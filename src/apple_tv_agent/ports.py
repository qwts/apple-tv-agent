"""Dependency seams; no protocol library, credential backend or LAN imports."""

from dataclasses import dataclass, field
from typing import Protocol

from apple_tv_agent.models import DeviceRecord, DiscoveredDevice, Model, ProtocolName
from apple_tv_agent.request import Request


@dataclass(frozen=True)
class Credentials:
    values: dict[ProtocolName, str] = field(repr=False)


@dataclass(frozen=True)
class CommandResult:
    device_id: str | None
    data: Model


class Adapter(Protocol):
    """One-shot operations own bounded sessions and cleanup in the future adapter."""

    async def discover(self, *, host: str | None, timeout: float) -> list[DiscoveredDevice]: ...

    async def execute(
        self, request: Request, device: DeviceRecord, credentials: Credentials
    ) -> CommandResult: ...


class Registry(Protocol):
    async def snapshot(self): ...
    async def register(self, candidate: DiscoveredDevice) -> DeviceRecord: ...
    async def alias(self, explicit: str | None, name: str) -> DeviceRecord: ...
    async def set_default(self, explicit: str | None) -> str: ...
    async def mark_paired(self, device_id: str, protocol: ProtocolName) -> None: ...
    async def remove(self, device_id: str) -> bool: ...


class CredentialStore(Protocol):
    def get(self, device_id: str, protocol: ProtocolName) -> str | None: ...
    def set(self, device_id: str, protocol: ProtocolName, value: str) -> None: ...
    def delete(self, device_id: str, protocol: ProtocolName) -> None: ...


class Service(Protocol):
    async def execute(self, request: Request) -> CommandResult: ...
