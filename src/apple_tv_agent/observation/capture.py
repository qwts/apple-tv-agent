"""Explicit bindings and one-shot capture; no Apple TV control is dispatched here."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Model
from apple_tv_agent.observation.artifacts import ArtifactStore
from apple_tv_agent.observation.discovery import Candidate, inspect_certificate
from apple_tv_agent.observation.images import decode_image, fetch_image, image_url, require_decoder
from apple_tv_agent.observation.models import ScreenBinding, ScreenObservation
from apple_tv_agent.observation.pairing import approve, selected
from apple_tv_agent.observation.registry import LGCredentials, LGRegistry
from apple_tv_agent.observation.ssap import pinned_socket, read, register
from apple_tv_agent.pairing import private_protocol_logs
from apple_tv_agent.registry import DeviceRegistry


class BindingRecord(Model):
    binding: ScreenBinding
    image_port: int = Field(strict=True, ge=1, le=65535)
    image_certificate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class BindingData(Model):
    schema_version: Literal[1] = 1
    bindings: list[BindingRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if len({r.binding.binding_id for r in self.bindings}) != len(self.bindings):
            raise ValueError("Duplicate bindings")
        if len({(r.binding.apple_tv_id, r.binding.lg_device_id) for r in self.bindings}) != len(
            self.bindings
        ):
            raise ValueError("Conflicting bindings")
        return self


class BindingRegistry(LGRegistry):
    data_model = BindingData

    def __init__(self, path=None):
        super().__init__(path)
        if path is None:
            self.path = self.path.with_name("screen-bindings.json")


class CaptureService:
    def __init__(
        self, *, lg=None, apple=None, bindings=None, artifacts=None, vault_factory=LGCredentials
    ):
        self.lg = LGRegistry() if lg is None else lg
        self.apple = DeviceRegistry() if apple is None else apple
        self.bindings = BindingRegistry() if bindings is None else bindings
        self.artifacts = ArtifactStore() if artifacts is None else artifacts
        self.vault_factory = vault_factory

    @asynccontextmanager
    async def authenticated(self, record, deadline):
        await selected(record.host, record.udn, deadline)
        with private_protocol_logs():
            async with pinned_socket(
                record.host, record.certificate_sha256, deadline=deadline
            ) as ws:
                key = self.vault_factory().get(str(record.device_id), "ssap")
                if not key:
                    raise AgentError(ErrorCode.PAIRING_REQUIRED)
                if await register(ws, key) != key:
                    raise AgentError(ErrorCode.AUTH_FAILED)
                yield ws

    async def apple_exists(self, device_id):
        data = await self.apple.snapshot()
        if not any(d.device_id == str(device_id) for d in data.devices):
            raise AgentError(ErrorCode.DEVICE_NOT_FOUND)

    def lg_record(self, data, device_id):
        record = next((d for d in data.devices if d.device_id == UUID(str(device_id))), None)
        if record is None or not record.paired:
            raise AgentError(ErrorCode.PAIRING_REQUIRED)
        return record

    async def bind(self, device_id, apple_id, hdmi, timeout=15, *, approval=approve):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            async with asyncio.timeout_at(deadline):
                await self.apple_exists(apple_id)
                snapshot = await self.lg.snapshot()
                record = self.lg_record(snapshot, device_id)
                async with self.authenticated(record, deadline) as ws:
                    info = await read(ws, "capture")
                    port = image_url(info.get("imageUri"), record.host)
                fingerprint = await inspect_certificate(record.host, port=port, deadline=deadline)
            if fingerprint != record.certificate_sha256:
                # Only certificate inspection happened; no image URL/request sent to this service yet.
                candidate = Candidate(
                    record.host, record.udn, f"LG HTTPS image service, port {port}", "image-service"
                )
                await approval(candidate, fingerprint)
            deadline = loop.time() + timeout
            async with asyncio.timeout_at(deadline):
                # Recheck the pairing after human interaction; never persist trust for a replaced record.
                async with self.lg.transaction() as current:
                    if self.lg_record(current, device_id) != record:
                        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
                    await self.apple_exists(apple_id)
                    async with self.bindings.transaction() as data:
                        binding = ScreenBinding(
                            binding_id=uuid4(),
                            apple_tv_id=apple_id,
                            lg_device_id=device_id,
                            hdmi_input=f"com.webos.app.hdmi{hdmi}",
                        )
                        new = BindingRecord(
                            binding=binding, image_port=port, image_certificate_sha256=fingerprint
                        )
                        old = next(
                            (
                                r
                                for r in data.bindings
                                if r.binding.apple_tv_id == binding.apple_tv_id
                                and r.binding.lg_device_id == binding.lg_device_id
                            ),
                            None,
                        )
                        if (
                            old is not None
                            and old.binding.hdmi_input == binding.hdmi_input
                            and old.image_port == port
                            and old.image_certificate_sha256 == fingerprint
                        ):
                            return old.model_dump(mode="json")
                        if old is not None:
                            data.bindings.remove(old)
                        data.bindings.append(new)
                        self.bindings._write(data)
                        return new.model_dump(mode="json")
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None

    async def unbind(self, binding_id, timeout=15):
        try:
            async with asyncio.timeout(timeout):
                async with self.bindings.transaction() as data:
                    data.bindings = [
                        r for r in data.bindings if str(r.binding.binding_id) != str(binding_id)
                    ]
                    self.bindings._write(data)
                    return {"binding_id": str(binding_id), "removed": True}
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None

    async def observe(self, binding, *, deadline):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise AgentError(ErrorCode.TIMEOUT)
        data = await self.capture(binding.binding_id, timeout=remaining, expected_binding=binding)
        return ScreenObservation.model_validate(data)

    async def discard(self, observation, *, deadline):
        if observation.artifact.path != str(
            self.artifacts.path(observation.observation_id).absolute()
        ):
            raise AgentError(ErrorCode.CONFIG_ERROR)
        async with asyncio.timeout_at(deadline):
            await self.artifacts.discard(observation.observation_id)

    async def capture(self, binding_id, timeout=15, *, expected_binding=None):
        require_decoder()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        observation_id = uuid4()
        saved = False
        try:
            async with asyncio.timeout_at(deadline):
                await self.artifacts.cleanup()
                async with self.lg.transaction() as lg_data:
                    async with self.bindings.transaction() as binding_data:
                        chosen = next(
                            (
                                r
                                for r in binding_data.bindings
                                if str(r.binding.binding_id) == str(binding_id)
                            ),
                            None,
                        )
                        if chosen is None:
                            raise AgentError(ErrorCode.DEVICE_NOT_FOUND)
                        if expected_binding is not None and chosen.binding != expected_binding:
                            raise AgentError(ErrorCode.IDENTITY_MISMATCH)
                        await self.apple_exists(chosen.binding.apple_tv_id)
                        record = self.lg_record(lg_data, chosen.binding.lg_device_id)
                        async with self.authenticated(record, deadline) as ws:
                            started = datetime.now(UTC)
                            frame_deadline = min(deadline, loop.time() + 9)
                            before = (await read(ws, "foreground")).get("appId")
                            if before != chosen.binding.hdmi_input:
                                raise AgentError(
                                    ErrorCode.FEATURE_UNAVAILABLE,
                                    details={"reason": "input_mismatch"},
                                )
                            info = await read(ws, "capture")
                            raw = await fetch_image(
                                info.get("imageUri"),
                                record.host,
                                chosen.image_port,
                                chosen.image_certificate_sha256,
                                deadline=frame_deadline,
                            )
                            after = (await read(ws, "foreground")).get("appId")
                            if after != before:
                                raise AgentError(
                                    ErrorCode.FEATURE_UNAVAILABLE,
                                    details={"reason": "input_mismatch"},
                                )
                        image = await decode_image(raw, deadline=frame_deadline)
                        if loop.time() >= frame_deadline:
                            raise AgentError(ErrorCode.TIMEOUT)
                        received = datetime.now(UTC)
                        expires = started + timedelta(seconds=10)
                        delete_after = received + timedelta(minutes=5)
                        path = await self.artifacts.save(
                            observation_id, raw, delete_after=delete_after
                        )
                        saved = True
                        observation = ScreenObservation(
                            observation_id=observation_id,
                            binding=chosen.binding,
                            started_at=started,
                            received_at=received,
                            expires_at=expires,
                            observed_input_before=before,
                            observed_input_after=after,
                            quality=image["quality"],
                            artifact={
                                "path": path,
                                "width": image["width"],
                                "height": image["height"],
                                "byte_count": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest(),
                                "delete_after": delete_after,
                            },
                        )
                        # Persisting an artifact must not turn an expired image into successful context.
                        if loop.time() >= frame_deadline:
                            raise AgentError(ErrorCode.TIMEOUT)
                        return observation.model_dump(mode="json")
        except BaseException as error:
            if saved:
                await self.artifacts.discard(observation_id)
            if isinstance(error, TimeoutError):
                raise AgentError(ErrorCode.TIMEOUT) from None
            raise
