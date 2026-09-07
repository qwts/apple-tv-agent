"""Offline trust, protocol, native namespace and recoverable registry tests."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import aiohttp
import pytest

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation import cli, pairing, ssap
from apple_tv_agent.observation.discovery import Candidate
from apple_tv_agent.observation.registry import LGCredentials, LGData, LGRecord, LGRegistry

HOST = "192.168.1.10"
UDN = "uuid:01234567-89ab-cdef-0123-456789abcdef"
PIN = "a" * 64
KEY = "synthetic-private-key"


class Socket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def receive(self):
        value = next(self.messages)
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(value))


def registered(key=KEY):
    return {"id": "register", "type": "registered", "payload": {"client-key": key}}


def prompt():
    return {"id": "register", "type": "response", "payload": {"pairingType": "PROMPT"}}


def test_registration_waits_for_tv_approval():
    ws = Socket([prompt(), registered()])
    assert asyncio.run(ssap.register(ws)) == KEY
    assert "client-key" not in ws.sent[0]["payload"]


def test_saved_auth_cannot_silently_repair():
    ws = Socket([prompt()])
    with pytest.raises(AgentError) as error:
        asyncio.run(ssap.register(ws, KEY))
    assert error.value.code == ErrorCode.AUTH_FAILED
    assert len(ws.sent) == 1


@pytest.mark.parametrize(
    "value",
    [None, "", 1, "\n", "x" * 4097],
    ids=["missing", "empty", "number", "control", "oversized"],
)
def test_malformed_registered_key(value):
    with pytest.raises(AgentError):
        asyncio.run(ssap.register(Socket([registered(value)])))


def test_peer_error_is_redacted():
    ws = Socket([{"id": "register", "type": "error", "error": KEY}])
    with pytest.raises(AgentError) as error:
        asyncio.run(ssap.register(ws))
    assert KEY not in str(error.value)


def test_read_allowlist_rejects_before_send():
    ws = Socket([])
    with pytest.raises(AgentError):
        asyncio.run(ssap.read(ws, "ssap://system/turnOff"))
    assert ws.sent == []


@pytest.mark.parametrize(
    "response,code",
    [
        ({"type": "error", "payload": {"returnValue": False}}, ErrorCode.FEATURE_UNAVAILABLE),
        ({"type": "response", "payload": {"returnValue": False}}, ErrorCode.NETWORK_ERROR),
        ({"type": "response", "payload": []}, ErrorCode.NETWORK_ERROR),
    ],
)
def test_read_permissions_and_shape(response, code):
    with pytest.raises(AgentError) as error:
        asyncio.run(ssap.read(Socket([{"id": "system", **response}]), "system"))
    assert error.value.code == code


def test_redirects_are_rejected():
    with pytest.raises(AgentError) as error:
        asyncio.run(ssap.reject_redirect(None, None, None))
    assert error.value.code == ErrorCode.IDENTITY_MISMATCH


def test_native_lg_namespace_and_roundtrip():
    vault = object.__new__(LGCredentials)
    saved = {}
    vault.backend = Mock()
    vault.backend.get_password.side_effect = lambda service, account: saved.get((service, account))
    vault.backend.set_password.side_effect = lambda service, account, value: saved.__setitem__(
        (service, account), value
    )
    vault.backend.delete_password.side_effect = lambda service, account: saved.pop(
        (service, account), None
    )
    device = str(uuid4())
    vault.set(device, "ssap", KEY)
    assert saved == {("apple-tv-agent-lg", f"{device}:ssap"): KEY}
    vault.delete(device, "ssap")
    vault.delete(device, "ssap")
    assert not saved


@pytest.fixture
def setup(tmp_path, monkeypatch):
    registry = LGRegistry(tmp_path / "lg.json")
    vault = Mock()
    vault.get.return_value = KEY
    monkeypatch.setattr(pairing.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        pairing, "selected", AsyncMock(return_value=Candidate(HOST, UDN, "Test", "LG"))
    )
    monkeypatch.setattr(pairing, "inspect_certificate", AsyncMock(return_value=PIN))
    monkeypatch.setattr(pairing, "register", AsyncMock(return_value=KEY))
    monkeypatch.setattr(pairing, "read", AsyncMock(return_value={"returnValue": True}))
    events = []

    @asynccontextmanager
    async def socket(*args, **kwargs):
        events.append("pin_verified")
        try:
            yield object()
        finally:
            events.append("closed")

    monkeypatch.setattr(pairing, "pinned_socket", socket)
    service = pairing.PairingService(registry, lambda: vault)
    return service, registry, vault, events


def pair(service):
    return asyncio.run(service.pair(HOST, UDN, approval=AsyncMock()))


def test_pair_verify_order_and_forget(setup):
    service, registry, vault, events = setup
    result = pair(service)
    device = result["device_id"]
    assert result["paired"]
    assert KEY not in registry.path.read_text()
    assert json.loads(registry.path.read_text())["devices"][0]["paired"] is True
    events.clear()
    vault.get.side_effect = lambda *args: events.append("key_read") or KEY
    assert asyncio.run(service.verify(device))["verified"]
    assert events == ["pin_verified", "key_read", "closed"]
    assert asyncio.run(service.forget(device))["tv_revocation_verified"] is False
    assert asyncio.run(service.forget(device))["removed_locally"]
    assert asyncio.run(registry.snapshot()).devices == []


def test_pin_failure_never_reads_vault(setup, monkeypatch):
    service, _, vault, _ = setup
    device = pair(service)["device_id"]
    vault.reset_mock()

    @asynccontextmanager
    async def bad_pin(*args, **kwargs):
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
        yield

    monkeypatch.setattr(pairing, "pinned_socket", bad_pin)
    with pytest.raises(AgentError):
        asyncio.run(service.verify(device))
    vault.get.assert_not_called()


def test_identity_failure_never_connects_or_reads_key(setup, monkeypatch):
    service, _, vault, _ = setup
    device = pair(service)["device_id"]
    vault.reset_mock()
    monkeypatch.setattr(
        pairing, "selected", AsyncMock(side_effect=AgentError(ErrorCode.IDENTITY_MISMATCH))
    )
    connect = Mock()
    monkeypatch.setattr(pairing, "pinned_socket", connect)
    with pytest.raises(AgentError):
        asyncio.run(service.verify(device))
    connect.assert_not_called()
    vault.get.assert_not_called()


def test_vault_failure_retains_pending_record(setup):
    service, registry, vault, _ = setup
    vault.set.side_effect = AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE)
    with pytest.raises(AgentError):
        pair(service)
    record = asyncio.run(registry.snapshot()).devices[0]
    assert not record.paired
    assert KEY not in registry.path.read_text()
    asyncio.run(service.forget(str(record.device_id)))


def test_forget_failure_preserves_registration(setup):
    service, registry, vault, _ = setup
    device = pair(service)["device_id"]
    before = registry.path.read_bytes()
    vault.delete.side_effect = AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE)
    with pytest.raises(AgentError):
        asyncio.run(service.forget(device))
    assert registry.path.read_bytes() == before


def test_changed_certificate_cannot_be_retrusted_implicitly(setup, monkeypatch):
    service, registry, _, _ = setup
    pair(service)
    before = registry.path.read_bytes()
    monkeypatch.setattr(pairing, "inspect_certificate", AsyncMock(return_value="b" * 64))
    approval = AsyncMock()
    with pytest.raises(AgentError) as error:
        asyncio.run(service.pair(HOST, UDN, approval=approval))
    assert error.value.code == ErrorCode.IDENTITY_MISMATCH
    approval.assert_not_called()
    assert registry.path.read_bytes() == before


def test_cancel_closes_session_retains_cleanup_uuid(setup, monkeypatch):
    service, registry, vault, events = setup
    monkeypatch.setattr(pairing, "register", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        pair(service)
    assert events == ["pin_verified", "closed"]
    assert not asyncio.run(registry.snapshot()).devices[0].paired
    vault.set.assert_not_called()


def test_noninteractive_pairing_before_network(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    dispatch = AsyncMock()
    monkeypatch.setattr(cli, "dispatch", dispatch)
    assert cli.main(["pair", "--host", HOST, "--udn", UDN]) == 3
    dispatch.assert_not_called()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INTERACTIVE_REQUIRED"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":2,"devices":[]}',
        b'{"schema_version":1,"devices":[],"client-key":"synthetic"}',
        b'{"schema_version":1,"schema_version":1,"devices":[]}',
    ],
)
def test_invalid_registry_preserved(tmp_path, raw):
    registry = LGRegistry(tmp_path / "lg.json")
    registry.path.write_bytes(raw)
    with pytest.raises(AgentError):
        asyncio.run(registry.snapshot())
    assert registry.path.read_bytes() == raw


def test_duplicate_identity_registry_rejected():
    record = LGRecord(device_id=uuid4(), udn=UDN, host=HOST, certificate_sha256=PIN)
    with pytest.raises(ValueError):
        LGData(devices=[record, record])


def test_socket_uses_pin_and_rejects_redirect_trace(monkeypatch):
    captured = {}

    class Context:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            captured["closed"] = True

    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            captured["session_closed"] = True

        def ws_connect(self, url, **kwargs):
            captured.update(kwargs)
            captured["url"] = url
            return Context()

    monkeypatch.setattr(ssap.aiohttp, "ClientSession", Session)

    async def run():
        async with ssap.pinned_socket(HOST, PIN, deadline=asyncio.get_running_loop().time() + 1):
            assert captured["ssl"].fingerprint == bytes.fromhex(PIN)
            assert ssap.reject_redirect in captured["trace_configs"][0].on_request_redirect

    asyncio.run(run())
    assert captured["trust_env"] is False
    assert captured["closed"] and captured["session_closed"]
    assert captured["max_msg_size"] == 64 * 1024
