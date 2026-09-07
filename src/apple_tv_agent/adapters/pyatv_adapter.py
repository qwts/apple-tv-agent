"""Normalize discovery from the pinned pyatv release; never open a connection."""

import asyncio
import hashlib
import json
from ipaddress import IPv4Address

from pydantic import ValidationError

from apple_tv_agent.discovery import CANDIDATE_PREFIX
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import DiscoveredDevice, ProtocolName


def normalize(config):
    identifiers = {}
    pairing = {}
    for service in config.services:
        protocol = ProtocolName(service.protocol.name.lower())
        if service.identifier is not None:
            if protocol in identifiers and identifiers[protocol] != service.identifier:
                raise AgentError(ErrorCode.IDENTITY_MISMATCH)
            identifiers[protocol] = service.identifier
        pairing[protocol] = {"NotNeeded": "not_needed"}.get(
            service.pairing.name, service.pairing.name.lower()
        )
    if not identifiers:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH, details={"reason": "missing_identity"})
    digest = hashlib.sha256(json.dumps(identifiers, sort_keys=True).encode()).hexdigest()
    return DiscoveredDevice(
        candidate_id=CANDIDATE_PREFIX + digest,
        name=config.name,
        host=str(IPv4Address(config.address)),
        identifiers=identifiers,
        pairing=pairing,
    )


class PyatvAdapter:
    def session(self):
        from apple_tv_agent.adapters.session import OwnedSession

        return OwnedSession(self)

    async def discover(self, *, host: str | None, timeout: float):
        loop = asyncio.get_running_loop()
        started = loop.time()
        # No protocol imports during CLI parsing or local-only registry commands.
        import pyatv
        from pyatv.const import OperatingSystem

        try:
            hosts = [str(IPv4Address(host))] if host is not None else None
        except ValueError:
            raise AgentError(
                ErrorCode.INVALID_ARGUMENT, details={"reason": "literal_ipv4_required"}
            ) from None
        try:
            remaining = timeout - (loop.time() - started)
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                # Reserve part of the deadline for socket setup, service info and cleanup.
                configs = await pyatv.scan(loop, timeout=remaining * 0.75, hosts=hosts)
                return sorted(
                    [
                        normalize(config)
                        for config in configs
                        if config.device_info.operating_system == OperatingSystem.TvOS
                    ],
                    key=lambda candidate: (candidate.candidate_id, candidate.host),
                )
        except TimeoutError:
            raise
        except (OSError, ValidationError, ValueError):
            raise AgentError(
                ErrorCode.NETWORK_ERROR, details={"reason": "discovery_failed"}
            ) from None

    async def _identified_config(self, device, candidate, timeout):
        import pyatv

        from apple_tv_agent.discovery import resolve_identity

        async with asyncio.timeout(timeout):
            configs = await pyatv.scan(
                asyncio.get_running_loop(), hosts=[candidate.host], timeout=timeout * 0.6
            )
        observations = [normalize(config) for config in configs]
        resolved = resolve_identity(device, observations)
        return next(
            config
            for config, observed in zip(configs, observations, strict=True)
            if observed == resolved
        )

    async def _memory(self, config, credentials):
        from pyatv.storage.memory_storage import MemoryStorage

        storage = MemoryStorage()
        await storage.load()
        settings = await storage.get_settings(config)
        for protocol, value in credentials.values.items():
            getattr(settings.protocols, protocol.value).credentials = value
        config.apply(settings)
        return storage

    async def _verify(self, config, protocol, credentials, storage):
        from pyatv.const import Protocol

        selected = next(p for p in Protocol if p.name.lower() == protocol.value)
        if protocol == ProtocolName.AIRPLAY:
            # AirPlay's public connect may be a no-op: explicitly authenticate Pair-Verify.
            from pyatv.auth.hap_pairing import AuthenticationType, parse_credentials
            from pyatv.protocols.airplay.auth import verify_connection
            from pyatv.support.http import http_connect

            parsed = parse_credentials(credentials.values[protocol])
            if parsed.type not in (AuthenticationType.HAP, AuthenticationType.Legacy):
                raise AgentError(ErrorCode.AUTH_FAILED)
            service = config.get_service(selected)
            connection = await http_connect(str(config.address), service.port)
            try:
                await verify_connection(parsed, connection)
            finally:
                connection.close()
        else:
            # Keep setup handles before connecting so failure/cancellation can close them.
            from pyatv.core import create_core
            from pyatv.protocols import PROTOCOLS
            from pyatv.support.http import create_session

            session = await create_session()
            setups = []
            try:
                core = await create_core(
                    config,
                    config.get_service(selected),
                    settings=await storage.get_settings(config),
                    session_manager=session,
                )
                setups = list(PROTOCOLS[selected].setup(core))
                if not setups:
                    raise AgentError(ErrorCode.UNSUPPORTED_FEATURE)
                for setup in setups:
                    if not await setup.connect():
                        raise AgentError(ErrorCode.AUTH_FAILED)
            finally:
                try:
                    tasks = [task for setup in setups for task in setup.close()]
                    if tasks:
                        async with asyncio.timeout(5):
                            await asyncio.gather(*tasks)
                finally:
                    await session.close()

    async def pair_protocol(self, device, candidate, protocol, pin_reader, timeout):
        import pyatv
        from pyatv.const import PairingRequirement, Protocol
        from pyatv.exceptions import (
            AuthenticationError,
            BackOffError,
            ConnectionFailedError,
            ConnectionLostError,
            InvalidCredentialsError,
            NoCredentialsError,
            OperationTimeoutError,
            PairingError,
        )

        from apple_tv_agent.ports import Credentials

        handler = None
        try:
            async with asyncio.timeout(timeout):
                config = await self._identified_config(device, candidate, min(10, timeout))
                storage = await self._memory(config, Credentials({}))
                selected = next(p for p in Protocol if p.name.lower() == protocol.value)
                advertised = config.get_service(selected)
                if (
                    advertised is None
                    or not advertised.enabled
                    or advertised.pairing
                    not in (PairingRequirement.Mandatory, PairingRequirement.Optional)
                ):
                    raise AgentError(
                        ErrorCode.FEATURE_UNAVAILABLE,
                        details={"reason": "pairing_no_longer_available"},
                    )
                handler = await pyatv.pair(
                    config, selected, asyncio.get_running_loop(), storage=storage
                )
                if not handler.device_provides_pin:
                    raise AgentError(
                        ErrorCode.UNSUPPORTED_FEATURE, details={"reason": "device_pin_required"}
                    )
                await handler.begin()
                handler.pin(await pin_reader())
                await handler.finish()
                if not handler.has_paired or not handler.service.credentials:
                    raise AgentError(ErrorCode.AUTH_FAILED)
                credentials = Credentials({protocol: handler.service.credentials})
                storage = await self._memory(config, credentials)
                await self._verify(config, protocol, credentials, storage)
                return credentials
        except OperationTimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None
        except BackOffError:
            raise AgentError(ErrorCode.DEVICE_BUSY) from None
        except (ConnectionFailedError, ConnectionLostError):
            raise AgentError(ErrorCode.NETWORK_ERROR) from None
        except (AuthenticationError, PairingError, InvalidCredentialsError, NoCredentialsError):
            raise AgentError(ErrorCode.AUTH_FAILED) from None
        except TimeoutError:
            raise
        except OSError:
            raise AgentError(ErrorCode.NETWORK_ERROR) from None
        finally:
            if handler is not None:
                async with asyncio.timeout(5):
                    await handler.close()

    async def verify_saved(self, device, vault, timeout=15):
        """Read-only reconnect seam for validation and the upcoming session service."""
        from pyatv.exceptions import AuthenticationError

        from apple_tv_agent.discovery import resolve_identity
        from apple_tv_agent.pairing import private_protocol_logs
        from apple_tv_agent.ports import Credentials

        with private_protocol_logs():
            try:
                async with asyncio.timeout(timeout):
                    candidates = await self.discover(host=None, timeout=timeout * 0.5)
                    candidate = resolve_identity(device, candidates)
                    config = await self._identified_config(device, candidate, timeout * 0.25)
                    # Resolve again at connection time BEFORE any vault lookup.
                    values = {
                        protocol: vault.get(device.device_id, protocol)
                        for protocol in device.paired_protocols
                    }
                    if not values or not all(values.values()):
                        raise AgentError(ErrorCode.PAIRING_REQUIRED)
                    credentials = Credentials(values)
                    storage = await self._memory(config, credentials)
                    for protocol in values:
                        await self._verify(config, protocol, credentials, storage)
            except AuthenticationError:
                raise AgentError(ErrorCode.AUTH_FAILED) from None
            except TimeoutError:
                raise
            except OSError:
                raise AgentError(ErrorCode.NETWORK_ERROR) from None
