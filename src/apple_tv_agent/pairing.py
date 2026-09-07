"""Pairing orchestration: retain verified secrets, report partial results, serialize devices."""

import asyncio
import hashlib
import logging
import sys
from contextlib import contextmanager
from uuid import UUID

from apple_tv_agent.discovery import select_device, select_pairing_candidate
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.locking import device_lock
from apple_tv_agent.models import ForgetData, PairData, ProtocolName
from apple_tv_agent.ports import CommandResult


@contextmanager
def private_protocol_logs():
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


class PairingService:
    def __init__(self, adapter, registry, vault, *, pin_reader=None, attempt_timeout=120):
        from apple_tv_agent.pin import read_pin

        self.adapter, self.registry, self.vault = adapter, registry, vault
        self.pin_reader = pin_reader or read_pin
        self.attempt_timeout = attempt_timeout

    async def pair(self, request):
        states = {}
        device_id = None
        try:
            with private_protocol_logs():
                candidates = await self.adapter.discover(host=None, timeout=request.timeout)
                snapshot = await self.registry.snapshot()
                candidate = select_pairing_candidate(
                    snapshot.devices, snapshot.default_device_id, candidates, request.device
                )
                key = hashlib.sha256(candidate.candidate_id.encode()).hexdigest()
                async with device_lock(self.registry.path.parent / "locks", key):
                    device = await self.registry.register(candidate)
                    device_id = device.device_id
                    async with device_lock(self.registry.path.parent / "locks", device_id):
                        current = await self.registry.snapshot()
                        select_device(current.devices, None, device_id)
                        supported = (ProtocolName.AIRPLAY, ProtocolName.COMPANION, ProtocolName.MRP)
                        for protocol in supported:
                            requirement = candidate.pairing.get(protocol)
                            if requirement == "not_needed":
                                states[protocol] = "not_needed"
                                continue
                            if requirement not in ("mandatory", "optional"):
                                continue
                            states[protocol] = "failed"
                            # Checking the vault first avoids prompting when it is inaccessible.
                            previous = self.vault.get(device_id, protocol)
                            for attempt in range(3):
                                print(
                                    f"Pairing {protocol.value} (attempt {attempt + 1}/3).",
                                    file=sys.stderr,
                                    flush=True,
                                )
                                try:
                                    async with asyncio.timeout(self.attempt_timeout):
                                        credentials = await self.adapter.pair_protocol(
                                            device,
                                            candidate,
                                            protocol,
                                            self.pin_reader,
                                            self.attempt_timeout,
                                        )
                                    break
                                except AgentError as error:
                                    if (
                                        error.code != ErrorCode.AUTH_FAILED
                                        or error.details.get("reason")
                                        in ("canceled", "input_closed")
                                        or attempt == 2
                                    ):
                                        raise
                            # Adapter has authenticated a fresh session with these credentials.
                            self.vault.set(device_id, protocol, credentials.values[protocol])
                            try:
                                await self.registry.mark_paired(device_id, protocol)
                            except (Exception, asyncio.CancelledError):
                                if previous is None:
                                    self.vault.delete(device_id, protocol)
                                else:
                                    self.vault.set(device_id, protocol, previous)
                                raise
                            states[protocol] = "paired"
                        if not states:
                            raise AgentError(
                                ErrorCode.UNSUPPORTED_FEATURE,
                                details={"reason": "no_pairable_protocol"},
                            )
            return CommandResult(device_id, PairData(protocols=states))
        except (Exception, asyncio.CancelledError) as error:
            if isinstance(error, AgentError):
                code, details = error.code, error.details
            elif isinstance(error, TimeoutError):
                code, details = ErrorCode.TIMEOUT, {}
            elif isinstance(error, asyncio.CancelledError):
                code, details = ErrorCode.AUTH_FAILED, {"reason": "canceled"}
            else:
                code, details = ErrorCode.INTERNAL_ERROR, {}
            raise AgentError(
                code, details={**details, "device_id": device_id, "protocols": states}
            ) from None

    async def forget(self, request):
        snapshot = await self.registry.snapshot()
        try:
            device = select_device(snapshot.devices, snapshot.default_device_id, request.device)
            device_id = device.device_id
        except AgentError as selection_error:
            if selection_error.code != ErrorCode.DEVICE_NOT_FOUND:
                raise
            # An explicit UUID supports an idempotent retry after registry removal.
            try:
                device_id = str(UUID(request.device))
            except (ValueError, TypeError, AttributeError):
                raise AgentError(ErrorCode.DEVICE_NOT_FOUND) from None
        async with device_lock(self.registry.path.parent / "locks", device_id):
            failed, removed = [], []
            with private_protocol_logs():
                for protocol in ProtocolName:
                    try:
                        self.vault.delete(device_id, protocol)
                        removed.append(protocol.value)
                    except AgentError:
                        failed.append(protocol.value)
            if failed:
                raise AgentError(
                    ErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                    details={
                        "device_id": device_id,
                        "removed_protocols": removed,
                        "failed_protocols": failed,
                        "registry_removed": False,
                        "recovery": "Retry devices forget with this device UUID after unlocking the vault.",
                    },
                )
            try:
                cleared = await self.registry.remove(device_id)
            except AgentError as error:
                raise AgentError(
                    error.code,
                    details={
                        **error.details,
                        "device_id": device_id,
                        "local_credentials_removed": True,
                        "registry_removed": False,
                    },
                ) from None
        return CommandResult(
            device_id,
            ForgetData(
                local_credentials_removed=True, registry_removed=True, default_cleared=cleared
            ),
        )
