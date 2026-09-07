import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from apple_tv_agent.adapters.session import OwnedSession
from apple_tv_agent.cli import main
from apple_tv_agent.controls import CORE_CONTROLS
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Capability, Command, DiscoveredDevice, StatusData
from apple_tv_agent.registry import DeviceRegistry
from apple_tv_agent.request import Request
from apple_tv_agent.sessions import SessionService


def run(coro):
    return asyncio.run(coro)


def state(**updates):
    values = dict(
        observed_at=datetime.now(UTC),
        playback_state=None,
        power=None,
        title=None,
        artist=None,
        album=None,
        app_id=None,
        position=None,
        duration=None,
        volume=None,
        keyboard_focus="unknown",
        unavailable_fields={},
    )
    return StatusData(**(values | updates))


MAPPINGS = [
    (Command.UP, "remote_control", "up"),
    (Command.DOWN, "remote_control", "down"),
    (Command.LEFT, "remote_control", "left"),
    (Command.RIGHT, "remote_control", "right"),
    (Command.SELECT, "remote_control", "select"),
    (Command.MENU, "remote_control", "menu"),
    (Command.HOME, "remote_control", "home"),
    (Command.PLAY, "remote_control", "play"),
    (Command.PAUSE, "remote_control", "pause"),
    (Command.STOP, "remote_control", "stop"),
    (Command.NEXT, "remote_control", "next"),
    (Command.PREVIOUS, "remote_control", "previous"),
    (Command.POWER_ON, "power", "turn_on"),
    (Command.POWER_OFF, "power", "turn_off"),
    (Command.VOLUME_UP, "audio", "volume_up"),
    (Command.VOLUME_DOWN, "audio", "volume_down"),
    (Command.VOLUME_SET, "audio", "set_volume"),
]


def session_for(command, *, availability="available", observed=None):
    session = OwnedSession(None)
    session.facade = SimpleNamespace(
        remote_control=SimpleNamespace(), power=SimpleNamespace(), audio=SimpleNamespace()
    )
    for _, interface, method in MAPPINGS:
        setattr(getattr(session.facade, interface), method, AsyncMock())
    session.feature = lambda name: Capability(state=availability, reason=None)
    session.status = AsyncMock(return_value=observed or state())
    return session


@pytest.mark.parametrize("command,interface,method", MAPPINGS)
def test_every_core_mapping_dispatches_exactly_one_allowed_operation(command, interface, method):
    session = session_for(command)
    result = run(session.act(Request(command, level=42)))
    expected = (
        {"level": 42}
        if command == Command.VOLUME_SET
        else (
            {"await_new_state": False} if command in (Command.POWER_ON, Command.POWER_OFF) else {}
        )
    )
    getattr(getattr(session.facade, interface), method).assert_awaited_once_with(**expected)
    for other_command, other_interface, other_method in MAPPINGS:
        if other_command != command:
            getattr(getattr(session.facade, other_interface), other_method).assert_not_called()
    assert session.dispatched is True
    assert result.outcome == "sent"


@pytest.mark.parametrize("command", list(CORE_CONTROLS))
@pytest.mark.parametrize(
    "availability,code",
    [
        ("unsupported", ErrorCode.UNSUPPORTED_FEATURE),
        ("unavailable", ErrorCode.FEATURE_UNAVAILABLE),
        ("unknown", ErrorCode.FEATURE_UNAVAILABLE),
    ],
)
def test_capability_denial_never_dispatches(command, availability, code):
    session = session_for(command, availability=availability)
    with pytest.raises(AgentError) as error:
        run(session.act(Request(command, level=42)))
    assert error.value.code == code
    assert session.dispatched is False
    for _, interface, method in MAPPINGS:
        getattr(getattr(session.facade, interface), method).assert_not_called()


@pytest.mark.parametrize(
    "command,values",
    [
        (Command.PLAY, {"playback_state": "playing"}),
        (Command.PAUSE, {"playback_state": "paused"}),
        (Command.STOP, {"playback_state": "stopped"}),
        (Command.POWER_ON, {"power": "on"}),
        (Command.POWER_OFF, {"power": "off"}),
        (Command.VOLUME_SET, {"volume": 42}),
    ],
)
def test_confirmation_requires_matching_readback(command, values):
    observed = state(**values)
    session = session_for(command, observed=observed)
    result = run(session.act(Request(command, level=42)))
    assert result.outcome == "confirmed"
    assert result.observed_state == observed
    session = session_for(command, observed=state())
    assert run(session.act(Request(command, level=42))).outcome == "sent"


@pytest.mark.parametrize(
    "command,before,after,expected",
    [
        (Command.VOLUME_UP, 40, 41, "confirmed"),
        (Command.VOLUME_DOWN, 40, 39, "confirmed"),
        (Command.VOLUME_UP, 100, 100, "sent"),
        (Command.VOLUME_DOWN, 0, 0, "sent"),
        (Command.VOLUME_UP, None, 41, "sent"),
        (Command.VOLUME_DOWN, 40, None, "sent"),
        (Command.VOLUME_UP, 40, 39, "sent"),
        (Command.VOLUME_DOWN, 40, 41, "sent"),
    ],
)
def test_volume_steps_require_observed_direction(command, before, after, expected):
    session = session_for(command)
    session.status.side_effect = [state(volume=before), state(volume=after)]
    assert run(session.act(Request(command))).outcome == expected


@pytest.mark.parametrize("level", ["-1", "101", "nan", "inf", "-inf"])
def test_bad_volume_is_rejected_before_service_construction(level, capsys):
    factory = Mock()
    assert main(["volume", "set", "--level", level], service_factory=factory) == 2
    factory.assert_not_called()
    capsys.readouterr()


@pytest.mark.parametrize("level", [0, 100])
def test_volume_boundaries_are_valid(level):
    session = session_for(Command.VOLUME_SET, observed=state(volume=level))
    assert run(session.act(Request(Command.VOLUME_SET, level=level))).outcome == "confirmed"


@pytest.mark.parametrize(
    "failure", ["connect", "dispatch", "readback", "close", "timeout", "cancel"]
)
def test_mutations_never_retry_and_preserve_dispatch_uncertainty(tmp_path, failure):
    registry = DeviceRegistry(tmp_path / "registry.json")
    device = run(
        registry.register(
            DiscoveredDevice(
                candidate_id="candidate-test",
                name="test",
                host="192.0.2.1",
                identifiers={"airplay": "test"},
                pairing={},
            )
        )
    )
    session = session_for(Command.PLAY, observed=state(playback_state="playing"))
    session.connect = AsyncMock()
    session.close = AsyncMock()
    network = AgentError(ErrorCode.NETWORK_ERROR, retryable=True)
    if failure == "connect":
        session.connect.side_effect = network
    if failure == "dispatch":
        session.facade.remote_control.play.side_effect = network
    if failure == "readback":
        session.status.side_effect = network
    if failure == "close":
        session.close.side_effect = network
    if failure == "timeout":
        session.status.side_effect = TimeoutError()
    if failure == "cancel":
        session.status.side_effect = asyncio.CancelledError()
    factory = Mock(return_value=session)
    service = SessionService(SimpleNamespace(session=factory), registry, object())
    with pytest.raises(AgentError) as error:
        run(service.execute(Request(Command.PLAY, device=device.device_id)))
    assert error.value.details["outcome"] == ("not_sent" if failure == "connect" else "unknown")
    assert error.value.details["device_id"] == device.device_id
    assert error.value.retryable is False
    factory.assert_called_once()
    assert session.facade.remote_control.play.await_count == (0 if failure == "connect" else 1)
    session.close.assert_awaited_once()


@pytest.mark.parametrize(
    "command,values",
    [
        (Command.PLAY, {"playback_state": "paused"}),
        (Command.PAUSE, {"playback_state": "playing"}),
        (Command.STOP, {"playback_state": "playing"}),
        (Command.POWER_ON, {"power": "off"}),
        (Command.POWER_OFF, {"power": "on"}),
        (Command.VOLUME_SET, {"volume": 43}),
    ],
)
def test_mismatched_readback_is_sent(command, values):
    session = session_for(command, observed=state(**values))
    assert run(session.act(Request(command, level=42))).outcome == "sent"


@pytest.mark.parametrize("command", list(CORE_CONTROLS))
def test_vault_initialization_failure_is_not_sent(command, monkeypatch, capsys):
    import json

    from apple_tv_agent.credentials import vault_error
    from apple_tv_agent.service import ContractService

    failure = vault_error("native_backend_required")
    constructor = Mock(side_effect=failure)
    monkeypatch.setattr("apple_tv_agent.credentials.NativeCredentialStore", constructor)
    adapter = Mock()
    service = ContractService(adapter=adapter, registry=Mock())
    argv = command.value.split(".")
    if command == Command.VOLUME_SET:
        argv += ["--level", "42"]
    assert main(argv, service_factory=lambda: service) == 3
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert output.err == ""
    assert result["device_id"] is None
    assert result["error"] == {
        "code": "CREDENTIAL_STORE_UNAVAILABLE",
        "message": str(failure),
        "retryable": False,
        "details": {**failure.details, "device_id": None, "outcome": "not_sent"},
    }
    constructor.assert_called_once_with()
    adapter.session.assert_not_called()
