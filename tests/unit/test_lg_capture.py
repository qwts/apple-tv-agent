"""Synthetic capture, image and artifact tests. No LAN or real screenshots."""

import asyncio
import io
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from PIL import Image

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation import capture, images
from apple_tv_agent.observation.artifacts import ArtifactStore
from apple_tv_agent.observation.image_worker import decode
from apple_tv_agent.observation.models import ScreenBinding
from apple_tv_agent.observation.registry import LGRecord, LGRegistry


def jpeg(color="white", size=(32, 24)):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10/image",
        "https://192.168.1.11/image",
        "https://user:key@192.168.1.10/image",
        "https://192.168.1.10:0/image",
        "https://192.168.1.10:3001/image",
        "https://tv.local/image",
        "https://192.168.1.10/image#fragment",
        None,
    ],
)
def test_image_origin_and_port(url):
    with pytest.raises(AgentError):
        images.image_url(url, "192.168.1.10", 443)


def test_valid_url():
    assert (
        images.image_url("https://192.168.1.10:1234/image?token=synthetic", "192.168.1.10") == 1234
    )


@pytest.mark.parametrize(
    "raw",
    [b"garbage", jpeg()[:-2], jpeg()[:100] + b"\xff\xd9"],
    ids=["garbage", "missing-eoi", "truncated"],
)
def test_bad_images(raw):
    with pytest.raises(Exception):
        decode(raw)


def test_dimension_bounds_before_decode():
    with pytest.raises(ValueError):
        decode(jpeg(size=(8193, 1)))


def test_black_and_nonblack():
    assert decode(jpeg("black"))["quality"] == "black"
    assert decode(jpeg())["quality"] == "usable"


def test_real_decoder_process():
    async def run():
        return await images.decode_image(jpeg(), deadline=asyncio.get_running_loop().time() + 5)

    assert asyncio.run(run())["width"] == 32


def test_decoder_timeout_kills_and_reaps(monkeypatch):
    process = Mock()
    process.returncode = None

    async def block(raw):
        await asyncio.sleep(10)

    process.communicate = block
    process.wait = AsyncMock()
    monkeypatch.setattr(images.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))

    async def run():
        await images.decode_image(jpeg(), deadline=asyncio.get_running_loop().time() + 0.01)

    with pytest.raises(AgentError) as error:
        asyncio.run(run())
    assert error.value.code == ErrorCode.TIMEOUT
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


def test_artifact_lifecycle_and_collision(tmp_path):
    store = ArtifactStore(tmp_path / "captures")
    observation_id = uuid4()
    expires = datetime.now(UTC) + timedelta(minutes=5)

    async def run():
        path = await store.save(observation_id, jpeg(), delete_after=expires)
        assert store.path(observation_id).read_bytes() == jpeg()
        if os.name != "nt":
            assert store.path(observation_id).stat().st_mode & 0o777 == 0o600
            assert store.root.stat().st_mode & 0o777 == 0o700
        with pytest.raises(AgentError):
            await store.save(observation_id, b"replacement", delete_after=expires)
        assert await store.cleanup(now=expires - timedelta(seconds=1)) == 0
        assert await store.cleanup(now=expires) == 1
        assert not store.path(observation_id).exists()
        await store.discard(observation_id)
        return path

    assert os.path.isabs(asyncio.run(run()))


def test_discard_does_not_delete_unowned_file(tmp_path):
    store = ArtifactStore(tmp_path / "captures")
    store.root.mkdir()
    observation_id = uuid4()
    store.path(observation_id).write_bytes(b"unowned")
    asyncio.run(store.discard(observation_id))
    assert store.path(observation_id).read_bytes() == b"unowned"


def test_collision_not_added_to_inventory(tmp_path):
    store = ArtifactStore(tmp_path / "captures")
    store.root.mkdir()
    observation_id = uuid4()
    store.path(observation_id).write_bytes(b"unowned")
    with pytest.raises(AgentError):
        asyncio.run(store.save(observation_id, jpeg(), delete_after=datetime.now(UTC)))
    assert asyncio.run(store.registry.snapshot()).artifacts == []


@pytest.mark.skipif(
    os.name == "nt",
    reason="symlink creation requires Windows privilege; ACL path is tested separately",
)
def test_symlink_inventory_rejected(tmp_path):
    store = ArtifactStore(tmp_path / "captures")
    store.root.mkdir()
    target = tmp_path / "target"
    target.write_text("do not touch")
    store.registry.path.symlink_to(target)
    with pytest.raises(AgentError):
        asyncio.run(store.cleanup())
    assert target.read_text() == "do not touch"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    lg = LGRegistry(tmp_path / "lg.json")
    bindings = capture.BindingRegistry(tmp_path / "bindings.json")
    record = LGRecord(
        device_id=uuid4(),
        udn=f"uuid:{uuid4()}",
        host="192.168.1.10",
        certificate_sha256="a" * 64,
        paired=True,
    )
    binding = ScreenBinding(
        binding_id=uuid4(),
        apple_tv_id=uuid4(),
        lg_device_id=record.device_id,
        hdmi_input="com.webos.app.hdmi4",
    )

    async def populate():
        async with lg.transaction() as data:
            data.devices.append(record)
            lg._write(data)
        async with bindings.transaction() as data:
            data.bindings.append(
                capture.BindingRecord(
                    binding=binding, image_port=443, image_certificate_sha256="b" * 64
                )
            )
            bindings._write(data)

    asyncio.run(populate())
    service = capture.CaptureService(
        lg=lg, bindings=bindings, artifacts=ArtifactStore(tmp_path / "captures")
    )
    monkeypatch.setattr(service, "apple_exists", AsyncMock())

    @asynccontextmanager
    async def authenticated(*args):
        yield object()

    monkeypatch.setattr(service, "authenticated", authenticated)
    monkeypatch.setattr(
        capture,
        "read",
        AsyncMock(
            side_effect=[
                {"appId": binding.hdmi_input},
                {"imageUri": "https://192.168.1.10/image"},
                {"appId": binding.hdmi_input},
            ]
        ),
    )
    monkeypatch.setattr(capture, "fetch_image", AsyncMock(return_value=jpeg()))
    return service, binding


def test_capture_and_provider_discard(setup):
    service, binding = setup

    async def run():
        observation = await service.observe(
            binding, deadline=asyncio.get_running_loop().time() + 10
        )
        assert observation.eligible_context(binding, now=datetime.now(UTC))
        assert service.artifacts.path(observation.observation_id).exists()
        await service.discard(observation, deadline=asyncio.get_running_loop().time() + 2)
        assert not service.artifacts.path(observation.observation_id).exists()

    asyncio.run(run())


@pytest.mark.parametrize(
    "before,after",
    [("com.webos.app.hdmi1", "com.webos.app.hdmi4"), ("com.webos.app.hdmi4", "com.webos.app.home")],
)
def test_input_mismatch_no_artifact(setup, monkeypatch, before, after):
    service, binding = setup
    monkeypatch.setattr(
        capture,
        "read",
        AsyncMock(
            side_effect=[
                {"appId": before},
                {"imageUri": "https://192.168.1.10/image"},
                {"appId": after},
            ]
        ),
    )
    with pytest.raises(AgentError) as error:
        asyncio.run(service.capture(binding.binding_id))
    assert error.value.details["reason"] == "input_mismatch"
    assert not list(service.artifacts.root.glob("*.jpg"))
    if before != binding.hdmi_input:
        capture.fetch_image.assert_not_called()


def test_binding_replacement_rejects_prior_context(setup):
    service, binding = setup
    changed = binding.model_copy(update={"binding_id": uuid4()})
    with pytest.raises(AgentError):
        asyncio.run(service.capture(binding.binding_id, expected_binding=changed))


def test_bound_service_pin_used(setup):
    service, binding = setup
    result = asyncio.run(service.capture(binding.binding_id))
    assert capture.fetch_image.call_args.args[2:] == (443, "b" * 64)
    asyncio.run(service.artifacts.discard(result["observation_id"]))


def test_capture_cancellation_closes_without_file(setup, monkeypatch):
    service, binding = setup
    monkeypatch.setattr(capture, "fetch_image", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.capture(binding.binding_id))
    assert not list(service.artifacts.root.glob("*.jpg"))


@pytest.mark.parametrize("kind", ["chunks", "redirect", "oversized", "certificate", "cancel"])
def test_fetch_bounds_redirect_pin_and_cleanup(monkeypatch, kind):
    import aiohttp

    seen = {}

    class Response:
        status = 302 if kind == "redirect" else 200
        content_length = None
        content = None

        async def __aenter__(self):
            if kind == "certificate":
                raise aiohttp.ServerFingerprintMismatch(b"a" * 32, b"b" * 32, "192.168.1.10", 443)
            return self

        async def __aexit__(self, *args):
            seen["response_closed"] = True

        async def iter_chunked(self, size):
            if kind == "cancel":
                raise asyncio.CancelledError()
            if kind == "oversized":
                for _ in range(161):
                    yield b"x" * 65536
            else:
                raw = jpeg()
                yield raw[:5]
                yield raw[5:]

    class Session:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            seen["session_closed"] = True

        def get(self, url, **kwargs):
            seen.update(kwargs)
            response = Response()
            response.content = response
            return response

    monkeypatch.setattr(images.aiohttp, "ClientSession", Session)

    async def run():
        return await images.fetch_image(
            "https://192.168.1.10/frame",
            "192.168.1.10",
            443,
            "a" * 64,
            deadline=asyncio.get_running_loop().time() + 5,
        )

    if kind == "chunks":
        assert asyncio.run(run()) == jpeg()
    else:
        with pytest.raises(asyncio.CancelledError if kind == "cancel" else AgentError):
            asyncio.run(run())
    assert seen["allow_redirects"] is False
    assert seen["ssl"].fingerprint == bytes.fromhex("a" * 64)
    assert seen["auto_decompress"] is False
    assert seen["trust_env"] is False
    assert seen["session_closed"]
    if kind != "certificate":
        assert seen["response_closed"]


def test_bind_different_certificate_requires_approval(setup, monkeypatch):
    service, binding = setup
    monkeypatch.setattr(
        capture, "read", AsyncMock(return_value={"imageUri": "https://192.168.1.10:1234/frame"})
    )
    monkeypatch.setattr(capture, "inspect_certificate", AsyncMock(return_value="c" * 64))
    approval = AsyncMock(side_effect=AgentError(ErrorCode.INTERACTIVE_REQUIRED))
    before = service.bindings.path.read_bytes()
    with pytest.raises(AgentError):
        asyncio.run(service.bind(binding.lg_device_id, binding.apple_tv_id, 4, approval=approval))
    approval.assert_awaited_once()
    assert service.bindings.path.read_bytes() == before
    capture.fetch_image.assert_not_called()


def test_bind_same_certificate_does_not_reprompt(setup, monkeypatch):
    service, binding = setup
    monkeypatch.setattr(
        capture, "read", AsyncMock(return_value={"imageUri": "https://192.168.1.10:443/frame"})
    )
    monkeypatch.setattr(capture, "inspect_certificate", AsyncMock(return_value="a" * 64))
    approval = AsyncMock()
    result = asyncio.run(
        service.bind(binding.lg_device_id, binding.apple_tv_id, 3, approval=approval)
    )
    assert result["binding"]["hdmi_input"] == "com.webos.app.hdmi3"
    assert result["binding"]["binding_id"] != str(binding.binding_id)
    approval.assert_not_called()
