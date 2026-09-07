"""Separate nonsecret LG trust records, using the baseline cancellable file lock."""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Model
from apple_tv_agent.observation.discovery import local_host, uuid_udn
from apple_tv_agent.registry import DeviceRegistry, unique_fields


def config_error(reason):
    return AgentError(
        ErrorCode.CONFIG_ERROR,
        details={
            "reason": reason,
            "recovery": (
                "Preserve lg-registry.json before recovery. See the bundled "
                "apple_tv_agent/docs/lg-pairing.md, also available at "
                "https://github.com/qwts/apple-tv-agent/blob/main/docs/lg-pairing.md"
            ),
        },
    )


class LGCredentials(NativeCredentialStore):
    service = "apple-tv-agent-lg"

    @staticmethod
    def account(device_id, protocol):
        if protocol != "ssap":
            raise ValueError("Invalid LG protocol")
        return f"{UUID(str(device_id))}:ssap"


class LGRecord(Model):
    device_id: UUID
    udn: str
    host: str
    certificate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    paired: bool = Field(strict=True, default=False)

    @model_validator(mode="after")
    def identity(self):
        try:
            if uuid_udn(self.udn) != self.udn or local_host(self.host) != self.host:
                raise ValueError
        except Exception:
            raise ValueError("Invalid LG identity") from None
        return self


class LGData(Model):
    schema_version: Literal[1] = 1
    devices: list[LGRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_records(self):
        for name in ("device_id", "udn", "host"):
            if len({getattr(d, name) for d in self.devices}) != len(self.devices):
                raise ValueError("Conflicting LG registrations")
        return self


class LGRegistry(DeviceRegistry):
    def __init__(self, path=None):
        super().__init__(path)
        if path is None:
            self.path = self.path.with_name("lg-registry.json")

    @asynccontextmanager
    async def transaction(self):
        try:
            async with super().transaction() as data:
                yield data
        except AgentError as error:
            if error.code != ErrorCode.CONFIG_ERROR:
                raise
            reason = error.details.get("reason", "invalid_lg_registry")
            reason = {
                "invalid_registry": "invalid_lg_registry",
                "registry_io": "lg_registry_io",
            }.get(reason, reason)
            raise config_error(reason) from None

    def _read(self):
        try:
            return self._read_validated()
        except ValueError:
            raise config_error("invalid_lg_registry") from None

    def _read_validated(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
        except FileNotFoundError:
            return LGData()
        if len(raw) > 1024 * 1024:
            raise config_error("invalid_lg_registry")
        data = json.loads(raw, object_pairs_hook=unique_fields)
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
        ):
            raise config_error("unsupported_lg_schema")
        if set(data) != {"schema_version", "devices"}:
            raise config_error("invalid_lg_registry")
        return LGData.model_validate(data)

    def _write(self, data):
        validated = LGData.model_validate(data.model_dump())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".lg-registry-",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(validated.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
