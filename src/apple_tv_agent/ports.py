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
    def list_devices(self) -> list[DeviceRecord]: ...
    def get(self, device_id: str) -> DeviceRecord | None: ...
    def upsert(self, device: DeviceRecord) -> None: ...
    def get_default(self) -> str | None: ...
    def set_default(self, device_id: str | None) -> None: ...
    def delete(self, device_id: str) -> None: ...


class CredentialStore(Protocol):
    def get(self, device_id: str, protocol: ProtocolName) -> str | None: ...
    def set(self, device_id: str, protocol: ProtocolName, value: str) -> None: ...
    def delete(self, device_id: str, protocol: ProtocolName) -> None: ...


class Service(Protocol):
    async def execute(self, request: Request) -> CommandResult: ...
