"""Normalize discovery from the pinned pyatv release; never open a connection."""

import asyncio
import hashlib
import json
from ipaddress import IPv4Address

from pydantic import ValidationError

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
        candidate_id="candidate-" + digest,
        name=config.name,
        host=str(IPv4Address(config.address)),
        identifiers=identifiers,
        pairing=pairing,
    )


class PyatvAdapter:
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
