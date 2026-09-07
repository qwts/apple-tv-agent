import asyncio
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pyatv.const import FeatureName, FeatureState, PairingRequirement, Protocol

spec = importlib.util.spec_from_file_location(
    "transport_probe", Path(__file__).parents[1] / "tools" / "transport_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_vault_cleanup_on_bad_readback(monkeypatch):
    backend = Mock()
    backend.get_password.return_value = "incorrect"
    monkeypatch.setattr(probe, "native_vault", lambda: (backend, "test"))
    with pytest.raises(probe.ProbeError, match="VAULT_READBACK_FAILED"):
        probe.vault_roundtrip()
    backend.delete_password.assert_called_once()


def test_vault_roundtrip_uses_unique_namespace_and_deletes(monkeypatch):
    values = {}
    backend = Mock()
    backend.set_password.side_effect = lambda service, user, secret: values.update({(service, user): secret})
    backend.get_password.side_effect = lambda service, user: values.get((service, user))
    backend.delete_password.side_effect = lambda service, user: values.pop((service, user))
    monkeypatch.setattr(probe, "native_vault", lambda: (backend, "test"))
    assert probe.vault_roundtrip()["cleanup"] == "passed"
    assert values == {}
    assert backend.set_password.call_args.args[0] == "apple-tv-agent.transport-probe"


def test_native_vault_rejects_unrecognized_backend(monkeypatch):
    monkeypatch.setattr(probe.keyring, "get_keyring", lambda: object())
    with pytest.raises(probe.ProbeError, match="NATIVE_VAULT_REQUIRED"):
        probe.native_vault()


def test_errors_do_not_leak_exception_text(monkeypatch, capsys):
    def fail():
        raise RuntimeError("secret-sentinel")
    monkeypatch.setattr(probe, "environment", fail)
    assert probe.main(["environment"]) == 1
    output = capsys.readouterr()
    assert "secret-sentinel" not in output.out + output.err
    assert "RuntimeError" in output.out


def test_discovery_allowlists_output():
    device = SimpleNamespace(
        identifier="test-id", name="test", address="192.0.2.1",
        credentials="secret-sentinel", properties={"secret": "secret-sentinel"},
        device_info=SimpleNamespace(model=SimpleNamespace(name="Gen4K"),
                                    operating_system=SimpleNamespace(name="TvOS"),
                                    version="test-version"),
        services=[SimpleNamespace(protocol=Protocol.AirPlay,
                                  pairing=PairingRequirement.Mandatory,
                                  enabled=True, credentials="secret-sentinel")],
    )
    assert "secret-sentinel" not in str(probe.summarize_device(device))


def test_session_requires_tty_before_scan(monkeypatch):
    scan = AsyncMock()
    monkeypatch.setattr(probe.pyatv, "scan", scan)
    monkeypatch.setattr(probe.sys.stdin, "isatty", lambda: False)
    with pytest.raises(probe.ProbeError, match="INTERACTIVE_REQUIRED"):
        asyncio.run(probe.network_probe(SimpleNamespace(command="session")))
    scan.assert_not_called()


def test_pair_failure_closes_handler(monkeypatch):
    handler = SimpleNamespace(device_provides_pin=True, begin=AsyncMock(),
                              pin=Mock(), finish=AsyncMock(side_effect=RuntimeError()),
                              close=AsyncMock(), has_paired=False)
    monkeypatch.setattr(probe.pyatv, "pair", AsyncMock(return_value=handler))
    monkeypatch.setattr(probe, "read_pin", AsyncMock(return_value="1234"))
    device = Mock()
    device.get_service.return_value = SimpleNamespace(enabled=True, pairing=PairingRequirement.Mandatory)
    with pytest.raises(probe.ProbeError, match="PAIRING_AIRPLAY_FINISH_FAILED"):
        asyncio.run(probe.pair_once(device, Protocol.AirPlay, object(), 1))
    handler.finish.assert_awaited_once()
    handler.close.assert_awaited_once()


@pytest.mark.parametrize("available", [True, False])
def test_pause_never_retries_and_connection_closes(monkeypatch, available):
    connection = SimpleNamespace(
        features=Mock(), metadata=SimpleNamespace(playing=AsyncMock(return_value=
            SimpleNamespace(device_state=SimpleNamespace(name="Playing")))),
        remote_control=SimpleNamespace(pause=AsyncMock(side_effect=TimeoutError())),
        close=Mock(return_value=set()),
    )
    connection.features.all_features.return_value = {
        FeatureName.Pause: SimpleNamespace(state=FeatureState.Available)
    }
    connection.features.in_state.side_effect = lambda state, name: available and name == FeatureName.Pause
    monkeypatch.setattr(probe.pyatv, "connect", AsyncMock(return_value=connection))
    with pytest.raises(TimeoutError if available else probe.ProbeError):
        asyncio.run(probe.inspect_connection(object(), object(), 1, pause=True))
    assert connection.remote_control.pause.await_count == int(available)
    connection.close.assert_called_once()


def test_pin_timeout_restores_terminal(monkeypatch):
    restored = []
    @contextmanager
    def reader():
        try:
            yield lambda: ""
        finally:
            restored.append(True)
    monkeypatch.setattr(probe, "terminal_reader", reader)
    with pytest.raises(TimeoutError):
        asyncio.run(probe.read_pin(timeout=0.01))
    assert restored == [True]


@pytest.mark.parametrize("available", [True, False])
def test_play_checks_capability_and_confirms_readback(monkeypatch, available):
    connection = SimpleNamespace(
        features=Mock(), metadata=SimpleNamespace(playing=AsyncMock(return_value=
            SimpleNamespace(device_state=SimpleNamespace(name="Playing")))),
        remote_control=SimpleNamespace(play=AsyncMock()), close=Mock(return_value=set()),
    )
    connection.features.all_features.return_value = {}
    connection.features.in_state.side_effect = lambda state, name: available and name == FeatureName.Play
    monkeypatch.setattr(probe.pyatv, "connect", AsyncMock(return_value=connection))
    if available:
        result = asyncio.run(probe.inspect_connection(object(), object(), 1, play=True))
        assert result["play_outcome"] == "confirmed"
    else:
        with pytest.raises(probe.ProbeError, match="PLAY_UNAVAILABLE"):
            asyncio.run(probe.inspect_connection(object(), object(), 1, play=True))
    assert connection.remote_control.play.await_count == int(available)
    connection.close.assert_called_once()


def test_pin_is_not_echoed(monkeypatch, capsys):
    characters = iter("1234\n")
    @contextmanager
    def reader():
        yield lambda: next(characters)
    monkeypatch.setattr(probe, "terminal_reader", reader)
    assert asyncio.run(probe.read_pin()) == "1234"
    output = capsys.readouterr()
    assert "1234" not in output.out + output.err


@pytest.mark.parametrize("arguments", [
    ["discover", "--host", "::1"],
    ["discover", "--host", "example.com"],
    ["discover", "--timeout", "0"],
    ["discover", "--timeout", "121"],
])
def test_invalid_network_arguments(arguments):
    with pytest.raises(SystemExit) as error:
        probe.parser().parse_args(arguments)
    assert error.value.code == 2
