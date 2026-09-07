"""Versioned nonsecret registry. Transactions lock, validate, fsync, then replace."""

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from filelock import FileLock, Timeout
from platformdirs import user_config_path
from pydantic import Field, ValidationError, model_validator

from apple_tv_agent.discovery import (
    CANDIDATE_PREFIX,
    identity_matches,
    identity_overlaps,
    select_device,
)
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import DeviceRecord, DiscoveredDevice, Identifier, Model


class RegistryData(Model):
    schema_version: Literal[1] = 1
    devices: list[DeviceRecord] = Field(default_factory=list)
    default_device_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_identity(self):
        ids = [d.device_id for d in self.devices]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate device IDs")
        aliases = []
        for index, device in enumerate(self.devices):
            if str(UUID(device.device_id)) != device.device_id or not device.identifiers:
                raise ValueError("Invalid registered identity")
            if any(alias.startswith(CANDIDATE_PREFIX) for alias in device.aliases):
                raise ValueError("Reserved candidate alias")
            aliases.extend(device.aliases)
            if any(
                identity_overlaps(device.identifiers, other.identifiers)
                for other in self.devices[:index]
            ):
                raise ValueError("Shared protocol identity")
        if len(set(aliases)) != len(aliases) or set(aliases) & set(ids):
            raise ValueError("Ambiguous alias")
        if self.default_device_id is not None and self.default_device_id not in ids:
            raise ValueError("Missing default")
        return self


def config_error(reason):
    return AgentError(
        ErrorCode.CONFIG_ERROR,
        details={
            "reason": reason,
            "recovery": (
                "Preserve the registry before recovery. See the bundled "
                "apple_tv_agent/docs/registry.md, also available at "
                "https://github.com/qwts/apple-tv-agent/blob/main/docs/registry.md"
            ),
        },
    )


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate registry field")
        result[key] = value
    return result


class DeviceRegistry:
    def __init__(self, path: Path | None = None, *, timeout: float = 5):
        self.path = (
            path
            if path is not None
            else user_config_path("apple-tv-agent", appauthor=False, roaming=False)
            / "registry.json"
        )
        self.timeout = timeout

    @asynccontextmanager
    async def transaction(self):
        lock = FileLock(str(self.path) + ".lock")
        acquired = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            deadline = asyncio.get_running_loop().time() + self.timeout
            while not acquired:
                try:
                    lock.acquire(timeout=0)
                    acquired = True
                except Timeout:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise AgentError(
                            ErrorCode.DEVICE_BUSY, details={"reason": "registry_locked"}
                        ) from None
                    await asyncio.sleep(
                        min(0.05, max(0, deadline - asyncio.get_running_loop().time()))
                    )
            yield self._read()
        except (ValueError, ValidationError):
            raise config_error("invalid_registry") from None
        except OSError:
            raise config_error("registry_io") from None
        finally:
            if acquired:
                lock.release()

    def _read(self):
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return RegistryData()
        # Require an explicit version, even though the in-memory empty state has defaults.
        data = json.loads(raw, object_pairs_hook=unique_fields)
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data.get("schema_version") != 1
        ):
            raise config_error("unsupported_schema")
        if set(data) != {"schema_version", "devices", "default_device_id"}:
            raise config_error("invalid_registry")
        return RegistryData.model_validate(data)

    def _write(self, data):
        # Revalidate copies modified within a transaction before touching the old file.
        data = RegistryData.model_validate(data.model_dump())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".registry-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(data.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    async def snapshot(self):
        async with self.transaction() as data:
            return data.model_copy(deep=True)

    async def register(self, candidate: DiscoveredDevice):
        """Called explicitly by pairing; does not claim any credentials were saved."""
        async with self.transaction() as data:
            if not candidate.identifiers:
                raise AgentError(
                    ErrorCode.IDENTITY_MISMATCH, details={"reason": "missing_identity"}
                )
            matches = [
                d for d in data.devices if identity_overlaps(d.identifiers, candidate.identifiers)
            ]
            if len(matches) > 1 or any(
                not identity_matches(d.identifiers, candidate.identifiers) for d in matches
            ):
                raise AgentError(ErrorCode.IDENTITY_MISMATCH)
            if matches:
                device = matches[0]
                device.identifiers.update(candidate.identifiers)
                device.name = candidate.name
                device.last_host = candidate.host
            else:
                device = DeviceRecord(
                    device_id=str(uuid4()),
                    name=candidate.name,
                    aliases=[],
                    identifiers=dict(candidate.identifiers),
                    last_host=candidate.host,
                    paired_protocols=[],
                )
                data.devices.append(device)
            self._write(data)
            return device.model_copy(deep=True)

    async def alias(self, explicit: str | None, name: str):
        if name.startswith(CANDIDATE_PREFIX):
            raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "reserved_alias"})
        async with self.transaction() as data:
            device = select_device(data.devices, data.default_device_id, explicit)
            if any(
                name == other.device_id
                or (other.device_id != device.device_id and name in other.aliases)
                for other in data.devices
            ):
                raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "alias_in_use"})
            if name not in device.aliases:
                device.aliases.append(name)
                self._write(data)
            return device.model_copy(deep=True)

    async def set_default(self, explicit: str | None):
        async with self.transaction() as data:
            device = select_device(data.devices, data.default_device_id, explicit)
            data.default_device_id = device.device_id
            self._write(data)
            return device.device_id
