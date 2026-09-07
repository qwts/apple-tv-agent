"""Explicit local trust approval and recoverable native LG credential lifecycle."""

import asyncio
import json
import sys
from uuid import UUID, uuid4

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation.discovery import discover, inspect_certificate
from apple_tv_agent.observation.registry import LGCredentials, LGRecord, LGRegistry
from apple_tv_agent.observation.ssap import manifest, pinned_socket, read, register
from apple_tv_agent.pairing import private_protocol_logs
from apple_tv_agent.pin import terminal_reader


async def approve(candidate, fingerprint):
    if not sys.stdin.isatty():
        raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
    permissions = sorted(set(manifest()["permissions"] + manifest()["signed"]["permissions"]))
    print(
        "LG first-use trust (not independently authenticated):\n"
        + json.dumps(
            {
                "host": candidate.host,
                "udn": candidate.udn,
                "name": candidate.name,
                "certificate_sha256": fingerprint,
            },
            ensure_ascii=True,
        )
        + "\nThe standard manifest grants broad remote permissions, including input, power, "
        "settings and updates. This helper only performs registration and allowlisted reads.\n"
        + "Permissions: "
        + ", ".join(permissions)
        + "\nType trust and Enter to accept this identity/certificate/permission set "
        "(input hidden; 120 seconds), or anything else to cancel:",
        file=sys.stderr,
        flush=True,
    )
    try:
        async with asyncio.timeout(120):
            with terminal_reader() as poll:
                answer = ""
                while True:
                    char = poll()
                    if char in ("\r", "\n"):
                        if answer != "trust":
                            raise AgentError(ErrorCode.AUTH_FAILED)
                        return
                    if char in ("\x03", "\x04", "\x1a"):
                        raise AgentError(ErrorCode.AUTH_FAILED)
                    if char in ("\x08", "\x7f"):
                        answer = answer[:-1]
                    elif char:
                        answer += char
                        if len(answer) > 5:
                            raise AgentError(ErrorCode.AUTH_FAILED)
                    await asyncio.sleep(0.02)
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    finally:
        print(file=sys.stderr)


async def selected(host, udn, deadline):
    candidates = await discover(host=host, deadline=deadline)
    matches = [c for c in candidates if c.udn == udn]
    if len(matches) != 1:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    return matches[0]


def existing(data, udn, host, fingerprint):
    match = next((d for d in data.devices if d.udn == udn), None)
    if any(d.host == host and d is not match for d in data.devices):
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    if match is not None and match.certificate_sha256 != fingerprint:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    return match


class PairingService:
    def __init__(self, registry=None, vault_factory=LGCredentials):
        self.registry = LGRegistry() if registry is None else registry
        self.vault_factory = vault_factory

    async def pair(self, host, udn, timeout=15, *, approval=approve):
        if not sys.stdin.isatty():
            raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            async with asyncio.timeout_at(deadline):
                candidate = await selected(host, udn, deadline)
                fingerprint = await inspect_certificate(host, deadline=deadline)
                snapshot = await self.registry.snapshot()
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None
        record = existing(snapshot, udn, host, fingerprint)
        if record is not None and record.paired:
            raise AgentError(ErrorCode.INVALID_ARGUMENT)
        await approval(candidate, fingerprint)
        # A separate 120-second human TV-approval budget follows local trust approval.
        deadline = loop.time() + 120
        try:
            async with asyncio.timeout_at(deadline):
                async with self.registry.transaction() as data:
                    record = existing(data, udn, host, fingerprint)
                    if record is not None and record.paired:
                        raise AgentError(ErrorCode.INVALID_ARGUMENT)
                    if record is None:
                        record = LGRecord(
                            device_id=uuid4(), udn=udn, host=host, certificate_sha256=fingerprint
                        )
                        data.devices.append(record)
                    else:
                        record.host = host
                    # Retain UUID/trust on any later failure so forget can clean up keys.
                    self.registry._write(data)
                    with private_protocol_logs():
                        async with pinned_socket(host, fingerprint, deadline=deadline) as ws:
                            print(
                                "Approve the LG Remote App request on the selected TV.",
                                file=sys.stderr,
                                flush=True,
                            )
                            key = await register(ws)
                            await read(ws, "system")
                        self.vault_factory().set(str(record.device_id), "ssap", key)
                    record.paired = True
                    self.registry._write(data)
                    return {"device_id": str(record.device_id), "paired": True}
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None

    async def verify(self, device_id, host=None, timeout=15):
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            async with asyncio.timeout_at(deadline):
                async with self.registry.transaction() as data:
                    record = next(
                        (d for d in data.devices if d.device_id == UUID(str(device_id))), None
                    )
                    if record is None or not record.paired:
                        raise AgentError(ErrorCode.PAIRING_REQUIRED)
                    host = record.host if host is None else host
                    await selected(host, record.udn, deadline)
                    existing(data, record.udn, host, record.certificate_sha256)
                    with private_protocol_logs():
                        async with pinned_socket(
                            host, record.certificate_sha256, deadline=deadline
                        ) as ws:
                            # Deliberately after identity and connection-level pin verification.
                            key = self.vault_factory().get(str(record.device_id), "ssap")
                            if not key:
                                raise AgentError(ErrorCode.PAIRING_REQUIRED)
                            authenticated_key = await register(ws, key)
                            if authenticated_key != key:
                                raise AgentError(ErrorCode.AUTH_FAILED)
                            await read(ws, "system")
                    if record.host != host:
                        record.host = host
                        self.registry._write(data)
                    return {"device_id": str(record.device_id), "verified": True}
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None

    async def forget(self, device_id, timeout=15):
        try:
            async with asyncio.timeout(timeout):
                async with self.registry.transaction() as data:
                    self.vault_factory().delete(str(device_id), "ssap")
                    data.devices = [d for d in data.devices if str(d.device_id) != str(device_id)]
                    self.registry._write(data)
                    return {
                        "device_id": str(device_id),
                        "removed_locally": True,
                        "tv_revocation_verified": False,
                    }
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None
