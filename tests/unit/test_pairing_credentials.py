import asyncio
import logging
import secrets
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Command, DiscoveredDevice, ProtocolName
from apple_tv_agent.pairing import PairingService
from apple_tv_agent.ports import Credentials
from apple_tv_agent.registry import DeviceRegistry
from apple_tv_agent.request import Request


def run(coro):
    return asyncio.run(coro)


class Vault:
    def __init__(self):
        self.values = {}
        self.fail_get = self.fail_set = self.fail_delete = None

    def get(self, device, protocol):
        if self.fail_get == protocol:
            raise AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE)
        return self.values.get((device, protocol))

    def set(self, device, protocol, value):
        if self.fail_set == protocol:
            raise AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE)
        self.values[device, protocol] = value

    def delete(self, device, protocol):
        if self.fail_delete == protocol:
            raise AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE)
        self.values.pop((device, protocol), None)


@pytest.fixture
def setup(tmp_path):
    candidate = DiscoveredDevice(
        candidate_id="candidate-test",
        name="test",
        host="192.0.2.1",
        identifiers={"airplay": "test", "companion": "test-companion"},
        pairing={"airplay": "mandatory", "companion": "mandatory"},
    )
    vault = Vault()
    registry = DeviceRegistry(tmp_path / "registry.json")

    async def pair(device, candidate, protocol, reader, timeout):
        return Credentials({protocol: secrets.token_hex(32)})

    adapter = SimpleNamespace(
        discover=AsyncMock(return_value=[candidate]), pair_protocol=AsyncMock(side_effect=pair)
    )
    service = PairingService(adapter, registry, vault, pin_reader=AsyncMock())
    return service, candidate


def request(candidate):
    return Request(Command.PAIR, device=candidate.candidate_id, timeout=2)


def test_pair_saves_only_verified_results(setup, capsys):
    service, candidate = setup
    result = run(service.pair(request(candidate)))
    assert result.data.protocols == {"airplay": "paired", "companion": "paired"}
    device = run(service.registry.snapshot()).devices[0]
    assert set(device.paired_protocols) == {"airplay", "companion"}
    outputs = capsys.readouterr()
    public = outputs.out + outputs.err + service.registry.path.read_text() + repr(result)
    assert outputs.out == ""
    for value in service.vault.values.values():
        assert value not in public


def test_failed_repair_preserves_prior_values_and_limits_attempts(setup):
    service, candidate = setup
    first = run(service.pair(request(candidate)))
    original = dict(service.vault.values)
    service.adapter.pair_protocol.reset_mock()
    service.adapter.pair_protocol.side_effect = AgentError(ErrorCode.AUTH_FAILED)
    with pytest.raises(AgentError) as error:
        run(service.pair(request(candidate)))
    assert service.adapter.pair_protocol.await_count == 3
    assert error.value.details["protocols"] == {"airplay": "failed"}
    assert error.value.details["device_id"] == first.device_id
    assert service.vault.values == original


def test_partial_pairing_does_not_claim_full_success(setup):
    service, candidate = setup
    value = secrets.token_hex(32)
    service.adapter.pair_protocol.side_effect = [
        Credentials({ProtocolName.AIRPLAY: value}),
        AgentError(ErrorCode.AUTH_FAILED),
        AgentError(ErrorCode.AUTH_FAILED),
        AgentError(ErrorCode.AUTH_FAILED),
    ]
    with pytest.raises(AgentError) as error:
        run(service.pair(request(candidate)))
    assert error.value.details["protocols"] == {"airplay": "paired", "companion": "failed"}
    assert run(service.registry.snapshot()).devices[0].paired_protocols == ["airplay"]


@pytest.mark.parametrize("phase", ["get", "set"])
def test_vault_failure_stops_pairing_and_has_no_success_claim(setup, phase):
    service, candidate = setup
    setattr(service.vault, "fail_" + phase, ProtocolName.AIRPLAY)
    with pytest.raises(AgentError) as error:
        run(service.pair(request(candidate)))
    assert error.value.code == ErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    assert error.value.details["protocols"] == {"airplay": "failed"}
    assert service.adapter.pair_protocol.await_count == (0 if phase == "get" else 1)


def test_registry_failure_restores_previous_credential(setup, monkeypatch):
    service, candidate = setup
    run(service.pair(request(candidate)))
    original = dict(service.vault.values)
    monkeypatch.setattr(
        service.registry, "mark_paired", AsyncMock(side_effect=AgentError(ErrorCode.CONFIG_ERROR))
    )
    with pytest.raises(AgentError):
        run(service.pair(request(candidate)))
    assert service.vault.values == original


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(),
        asyncio.CancelledError(),
        AgentError(ErrorCode.AUTH_FAILED, details={"reason": "canceled"}),
    ],
)
def test_timeout_and_cancellation_do_not_retry_or_keep_lock(setup, failure):
    service, candidate = setup
    previous_logging = logging.root.manager.disable
    service.adapter.pair_protocol.side_effect = failure
    with pytest.raises(AgentError):
        run(service.pair(request(candidate)))
    assert service.adapter.pair_protocol.await_count == 1
    assert not service.vault.values
    assert logging.root.manager.disable == previous_logging
    service.adapter.pair_protocol.side_effect = None
    service.adapter.pair_protocol.return_value = Credentials(
        {ProtocolName.AIRPLAY: secrets.token_hex(32)}
    )
    candidate.pairing = {"airplay": "mandatory"}
    run(service.pair(request(candidate)))


def test_forget_partial_failure_retry_and_other_device_isolation(setup):
    service, candidate = setup
    result = run(service.pair(request(candidate)))
    run(service.registry.set_default(result.device_id))
    other = str(uuid4())
    other_value = secrets.token_hex(32)
    service.vault.values[other, ProtocolName.AIRPLAY] = other_value
    service.vault.fail_delete = ProtocolName.COMPANION
    req = Request(Command.DEVICES_FORGET, device=result.device_id)
    with pytest.raises(AgentError) as error:
        run(service.forget(req))
    assert error.value.details["failed_protocols"] == ["companion"]
    assert error.value.details["registry_removed"] is False
    assert run(service.registry.snapshot()).default_device_id == result.device_id
    service.vault.fail_delete = None
    forgotten = run(service.forget(req))
    assert forgotten.data.default_cleared is True
    assert run(service.registry.snapshot()).devices == []
    assert service.vault.values == {(other, ProtocolName.AIRPLAY): other_value}
    assert run(service.forget(req)).data.registry_removed is True


def test_forget_registry_failure_reports_secrets_already_removed(setup, monkeypatch):
    service, candidate = setup
    result = run(service.pair(request(candidate)))
    monkeypatch.setattr(
        service.registry, "remove", AsyncMock(side_effect=AgentError(ErrorCode.CONFIG_ERROR))
    )
    with pytest.raises(AgentError) as error:
        run(service.forget(Request(Command.DEVICES_FORGET, device=result.device_id)))
    assert error.value.details["local_credentials_removed"] is True
    assert error.value.details["registry_removed"] is False


def test_native_backend_rejects_unknown_backend(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_keyring", lambda: SimpleNamespace())
    with pytest.raises(AgentError) as error:
        NativeCredentialStore()
    assert error.value.details["reason"] == "native_backend_required"


class Backend:
    def __init__(self):
        self.values = {}
        self.failed = False

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[service, account] = value
        if self.failed:
            self.failed = False
            raise RuntimeError(value)

    def delete_password(self, service, account):
        self.values.pop((service, account), None)


@pytest.mark.parametrize("has_previous", [False, True])
def test_native_store_restores_after_partial_write(has_previous):
    # Bypass selection only to test persistence semantics with an isolated synthetic backend.
    store = NativeCredentialStore.__new__(NativeCredentialStore)
    store.backend = Backend()
    device = str(uuid4())
    previous = secrets.token_hex(32) if has_previous else None
    if previous:
        store.set(device, ProtocolName.AIRPLAY, previous)
    store.backend.failed = True
    value = secrets.token_hex(32)
    with pytest.raises(AgentError) as error:
        store.set(device, ProtocolName.AIRPLAY, value)
    assert store.get(device, ProtocolName.AIRPLAY) == previous
    assert value not in str(error.value)
    assert error.value.details["reason"] == "write_failed_previous_restored"


def test_pin_reader_never_echoes_and_handles_backspace(monkeypatch, capsys):
    from apple_tv_agent import pin

    value = str(secrets.randbelow(10000)).zfill(4)
    chars = iter(value[:2] + "0\x08" + value[2:] + "\n")

    @contextmanager
    def reader(stream):
        yield lambda: next(chars)

    monkeypatch.setattr(pin, "terminal_reader", reader)
    assert run(pin.read_pin()) == value
    output = capsys.readouterr()
    assert output.out == ""
    assert value not in output.err


def test_pin_reader_timeout_restores_terminal_context(monkeypatch):
    from apple_tv_agent import pin

    restored = []

    @contextmanager
    def reader(stream):
        try:
            yield lambda: ""
        finally:
            restored.append(True)

    monkeypatch.setattr(pin, "terminal_reader", reader)
    with pytest.raises(TimeoutError):
        run(pin.read_pin(timeout=0.02))
    assert restored == [True]


def test_forget_ambiguous_selection_is_preserved(setup):
    service, candidate = setup
    run(service.registry.register(candidate))
    other = candidate.model_copy(deep=True)
    other.identifiers = {"airplay": "other"}
    run(service.registry.register(other))
    with pytest.raises(AgentError) as error:
        run(service.forget(Request(Command.DEVICES_FORGET)))
    assert error.value.code == ErrorCode.DEVICE_AMBIGUOUS


@pytest.mark.parametrize("phase", ["begin", "finish", "verify", "success", "cancel"])
def test_adapter_handler_lifetime_and_verification_before_return(setup, monkeypatch, phase):
    from ipaddress import IPv4Address

    import pyatv
    from pyatv.conf import AppleTV, ManualService
    from pyatv.const import PairingRequirement, Protocol

    from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter

    service, candidate = setup
    device = run(service.registry.register(candidate))
    config = AppleTV(IPv4Address(candidate.host), "test")
    config.add_service(
        ManualService(
            "test", Protocol.AirPlay, 7000, {}, pairing_requirement=PairingRequirement.Mandatory
        )
    )
    protocol_service = config.get_service(Protocol.AirPlay)
    secret = secrets.token_hex(32)
    events = []

    class Handler:
        device_provides_pin = True
        has_paired = True
        service = protocol_service

        async def begin(self):
            events.append("begin")
            if phase == "begin":
                raise pyatv.exceptions.PairingError(secret)
            if phase == "cancel":
                raise asyncio.CancelledError

        def pin(self, value):
            events.append("pin")

        async def finish(self):
            events.append("finish")
            if phase == "finish":
                raise pyatv.exceptions.PairingError(secret)
            self.service.credentials = secret

        async def close(self):
            events.append("close")

    adapter = PyatvAdapter()
    monkeypatch.setattr(adapter, "_identified_config", AsyncMock(return_value=config))

    async def verify(*args):
        events.append("verify")
        if phase == "verify":
            raise pyatv.exceptions.AuthenticationError(secret)

    monkeypatch.setattr(adapter, "_verify", verify)
    monkeypatch.setattr(pyatv, "pair", AsyncMock(return_value=Handler()))
    coro = adapter.pair_protocol(
        device, candidate, ProtocolName.AIRPLAY, AsyncMock(return_value="0000"), 2
    )
    if phase == "success":
        credentials = run(coro)
        assert credentials.values[ProtocolName.AIRPLAY] == secret
        assert secret not in repr(credentials)
        assert events == ["begin", "pin", "finish", "verify", "close"]
    else:
        with pytest.raises((AgentError, asyncio.CancelledError)):
            run(coro)
        assert events[-1] == "close"


def test_reconnect_checks_identity_before_vault_access(setup, monkeypatch):
    from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter

    service, candidate = setup
    device = run(service.registry.register(candidate))
    device.paired_protocols = [ProtocolName.AIRPLAY]
    impostor = candidate.model_copy(deep=True)
    impostor.identifiers = {"airplay": "different"}
    adapter = PyatvAdapter()
    monkeypatch.setattr(adapter, "discover", AsyncMock(return_value=[impostor]))
    service.vault.get = lambda *args: pytest.fail("Vault read before identity check")
    with pytest.raises(AgentError) as error:
        run(adapter.verify_saved(device, service.vault))
    assert error.value.code == ErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("cancel", [False, True])
def test_protocol_verification_closes_partial_setup_on_failure(monkeypatch, cancel):
    from pyatv import core
    from pyatv.const import Protocol
    from pyatv.protocols import PROTOCOLS
    from pyatv.support import http

    from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter

    events = []

    async def connect():
        events.append("connect")
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("synthetic-failure")

    def close():
        events.append("close")
        return set()

    session = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(http, "create_session", AsyncMock(return_value=session))
    monkeypatch.setattr(core, "create_core", AsyncMock(return_value=object()))
    monkeypatch.setitem(
        PROTOCOLS,
        Protocol.Companion,
        SimpleNamespace(setup=lambda core: [SimpleNamespace(connect=connect, close=close)]),
    )
    config = SimpleNamespace(get_service=lambda protocol: object())
    storage = SimpleNamespace(get_settings=AsyncMock(return_value=object()))
    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        run(PyatvAdapter()._verify(config, ProtocolName.COMPANION, Credentials({}), storage))
    assert events == ["connect", "close"]
    session.close.assert_awaited_once()


def test_library_debug_secrets_are_suppressed_during_pairing(setup, capsys, caplog):
    service, candidate = setup
    secret = secrets.token_hex(32)

    async def noisy(*args):
        logging.getLogger("pyatv.synthetic").error(secret)
        raise RuntimeError(secret)

    service.adapter.pair_protocol.side_effect = noisy
    with pytest.raises(AgentError) as error:
        run(service.pair(request(candidate)))
    out = capsys.readouterr()
    assert secret not in out.out + out.err + caplog.text + str(error.value.details)


@pytest.mark.parametrize("interrupt", ["deadline", "cancel", "timeout_error"])
def test_forget_interruption_retains_completed_deletion_and_uuid_recovery(
    setup, monkeypatch, interrupt
):
    from filelock import FileLock

    from apple_tv_agent.cli import execute

    service, candidate = setup
    paired = run(service.pair(request(candidate)))
    run(service.registry.set_default(paired.device_id))
    original_remove = service.registry.remove

    async def exercise():
        waiting = asyncio.Event()

        async def blocked_remove(device_id):
            if interrupt == "timeout_error":
                raise TimeoutError
            with FileLock(str(service.registry.path) + ".lock"):
                waiting.set()
                return await original_remove(device_id)

        monkeypatch.setattr(service.registry, "remove", blocked_remove)
        req = Request(
            Command.DEVICES_FORGET,
            device=paired.device_id,
            timeout=0.05 if interrupt == "deadline" else 10,
        )
        task = asyncio.create_task(execute(SimpleNamespace(execute=service.forget), req))
        if interrupt == "cancel":
            await asyncio.wait_for(waiting.wait(), timeout=1)
            task.cancel()
        with pytest.raises(AgentError) as error:
            await task
        assert error.value.code == (
            ErrorCode.CONFIG_ERROR if interrupt == "cancel" else ErrorCode.TIMEOUT
        )
        assert error.value.details["device_id"] == paired.device_id
        assert error.value.details["local_credentials_removed"] is True
        assert error.value.details["registry_removed"] is False
        assert "UUID" in error.value.details["recovery"]
        assert not service.vault.values
        assert (await service.registry.snapshot()).default_device_id == paired.device_id
        monkeypatch.setattr(service.registry, "remove", original_remove)
        retried = await service.forget(req)
        assert retried.data.registry_removed is True
        assert retried.data.default_cleared is True

    run(exercise())
