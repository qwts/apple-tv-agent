import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apple_tv_agent.adapters.session import OwnedSession, public_error
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import CapabilitiesData, Command, DiscoveredDevice
from apple_tv_agent.registry import DeviceRegistry
from apple_tv_agent.request import Request
from apple_tv_agent.sessions import SessionService


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def selected(tmp_path):
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
    return registry, device


class FakeSession:
    def __init__(self, *, error=None, close_error=None, delay=0):
        self.error, self.close_error, self.delay = error, close_error, delay
        self.events = []
        self.ends = []

    async def connect(self, device, vault, end):
        self.events.append("connect")
        self.ends.append(end)

    async def capabilities(self):
        self.events.append("read")
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return CapabilitiesData(observed_at=datetime.now(UTC), features={})

    status = capabilities

    async def close(self, timeout):
        self.events.append("close")
        if self.close_error:
            raise self.close_error


@pytest.mark.parametrize(
    "error,retries",
    [
        (AgentError(ErrorCode.NETWORK_ERROR, retryable=True), 1),
        (AgentError(ErrorCode.AUTH_FAILED), 0),
        (AgentError(ErrorCode.NETWORK_ERROR), 0),
    ],
)
def test_safe_read_retry_keeps_deadline_and_closes_each_session(selected, error, retries):
    registry, device = selected
    sessions = [FakeSession(error=error), FakeSession()]
    created = []

    def factory():
        created.append(sessions[len(created)])
        return created[-1]

    service = SessionService(SimpleNamespace(session=factory), registry, object())
    req = Request(Command.CAPABILITIES, device=device.device_id)
    if retries:
        result = run(service.execute(req))
        assert result.device_id == device.device_id
        assert sessions[0].ends == sessions[1].ends
    else:
        with pytest.raises(AgentError) as result:
            run(service.execute(req))
        assert result.value.code == error.code
    assert len(created) == 1 + retries
    assert all(s.events == ["connect", "read", "close"] for s in created)


def test_timeout_and_cancellation_close_session_and_release_device_lock(selected):
    registry, device = selected
    session = FakeSession(delay=10)
    service = SessionService(SimpleNamespace(session=lambda: session), registry, object())
    with pytest.raises(AgentError) as error:
        run(service.execute(Request(Command.STATUS, device=device.device_id, timeout=0.08)))
    assert error.value.code == ErrorCode.TIMEOUT
    assert session.events[-1] == "close"
    session.delay = 0
    assert (
        run(service.execute(Request(Command.STATUS, device=device.device_id))).device_id
        == device.device_id
    )


def test_close_failure_cannot_be_success_or_retried(selected):
    registry, device = selected
    session = FakeSession(
        close_error=AgentError(ErrorCode.NETWORK_ERROR, details={"reason": "cleanup_failed"})
    )
    service = SessionService(SimpleNamespace(session=lambda: session), registry, object())
    with pytest.raises(AgentError) as error:
        run(service.execute(Request(Command.STATUS, device=device.device_id)))
    assert error.value.details["reason"] == "cleanup_failed"
    assert session.events == ["connect", "read", "close"]


def facade(states=None, **playing_values):
    from pyatv.const import DeviceState, KeyboardFocusState, PowerState

    states = states or {}
    values = dict(
        device_state=DeviceState.Paused,
        title="Untrusted title",
        artist=None,
        album=None,
        position=12.0,
        total_time=100.0,
    )
    values.update(playing_values)
    return SimpleNamespace(
        features=SimpleNamespace(
            get_feature=lambda feature: SimpleNamespace(
                state=SimpleNamespace(name=states.get(feature.name, "Available"))
            )
        ),
        metadata=SimpleNamespace(
            playing=AsyncMock(return_value=SimpleNamespace(**values)),
            app=SimpleNamespace(identifier="com.example.app"),
        ),
        power=SimpleNamespace(power_state=PowerState.On),
        keyboard=SimpleNamespace(text_focus_state=KeyboardFocusState.Unfocused),
        audio=SimpleNamespace(volume=42.0),
    )


def test_status_distinguishes_missing_unsupported_invalid_and_unknown():
    session = OwnedSession(None)
    session.facade = facade(
        {"Album": "Unsupported", "Position": "Unavailable", "TextFocusState": "Unknown"},
        total_time=float("nan"),
    )
    result = run(session.status())
    assert result.playback_state == "paused"
    assert result.title == "Untrusted title"
    assert result.artist is result.album is result.position is result.duration is None
    assert result.unavailable_fields == {
        "artist": "not_reported",
        "album": "unsupported",
        "position": "unavailable",
        "duration": "invalid_or_missing_value",
        "keyboard_focus": "unknown",
    }
    assert result.power == "on"
    assert result.volume == 42
    assert result.observed_at.tzinfo is not None


def test_missing_metadata_does_not_hide_available_power():
    from pyatv.exceptions import NotSupportedError

    session = OwnedSession(None)
    session.facade = facade()
    session.facade.metadata.playing.side_effect = NotSupportedError()
    result = run(session.status())
    assert result.playback_state is None
    assert result.unavailable_fields["playback_state"] == "unsupported"
    assert result.power == "on"


@pytest.mark.parametrize("state", ["Unavailable", "Unsupported", "Unknown", "Unexpected"])
def test_nonavailable_features_never_become_available(state):
    session = OwnedSession(None)
    session.facade = facade({"Play": state})
    capabilities = run(session.capabilities())
    assert capabilities.features[Command.PLAY].state != "available"
    assert capabilities.features[Command.KEYBOARD_TYPE].state == "unavailable"
    assert capabilities.features[Command.KEYBOARD_TYPE].reason == "keyboard_not_focused"


def test_network_failure_is_error_not_partial_metadata():
    from pyatv.exceptions import ConnectionLostError

    session = OwnedSession(None)
    session.facade = facade()
    session.facade.metadata.playing.side_effect = ConnectionLostError("private-sentinel")
    with pytest.raises(AgentError) as error:
        run(session.status())
    assert error.value.code == ErrorCode.NETWORK_ERROR
    assert error.value.retryable is True
    assert "private-sentinel" not in str(error.value)


def test_owned_cleanup_closes_unconnected_setups_once():
    session = OwnedSession(None)
    events = []
    close = session._once(lambda: events.append("partial-closed") or set())
    session.closers = [close]
    session.facade = SimpleNamespace(close=lambda: close())
    session.http = SimpleNamespace(close=AsyncMock())
    run(session.close(1))
    assert events == ["partial-closed"]
    session.http.close.assert_awaited_once()


@pytest.mark.parametrize(
    "kind,code",
    [
        ("AuthenticationError", ErrorCode.AUTH_FAILED),
        ("InvalidCredentialsError", ErrorCode.AUTH_FAILED),
        ("BackOffError", ErrorCode.DEVICE_BUSY),
        ("ProtocolError", ErrorCode.NETWORK_ERROR),
        ("NoCredentialsError", ErrorCode.PAIRING_REQUIRED),
        ("OperationTimeoutError", ErrorCode.TIMEOUT),
    ],
)
def test_protocol_errors_are_classified_without_raw_text(kind, code):
    from pyatv import exceptions

    error = public_error(getattr(exceptions, kind)("private-sentinel"))
    assert error.code == code
    assert "private-sentinel" not in str(error) + str(error.details)


def hold_device_lock(directory, device_id, ready, release):
    from apple_tv_agent.locking import device_lock

    async def hold():
        async with device_lock(directory, device_id):
            ready.set()
            # This helper process deliberately owns the lock while the parent attempts a read.
            await asyncio.to_thread(release.wait, 10)

    run(hold())


def test_other_process_holding_device_lock_prevents_connection(selected):
    import multiprocessing

    registry, device = selected
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    worker = context.Process(
        target=hold_device_lock,
        args=(registry.path.parent / "locks", device.device_id, ready, release),
    )
    worker.start()
    try:
        assert ready.wait(10)

        def factory():
            pytest.fail("Connected while another process owned the device")

        service = SessionService(SimpleNamespace(session=factory), registry, object())
        with pytest.raises(AgentError) as error:
            run(service.execute(Request(Command.STATUS, timeout=0.2)))
        # A loaded runner can exhaust the overall deadline before the lock poll.
        # Both outcomes must prevent any connection while the other process owns it.
        assert error.value.code in (ErrorCode.DEVICE_BUSY, ErrorCode.TIMEOUT)
    finally:
        release.set()
        worker.join(10)
        if worker.is_alive():
            worker.terminate()
            worker.join()
        assert worker.exitcode == 0


def test_explicit_task_cancellation_cleans_up(selected):
    registry, device = selected
    session = FakeSession()

    async def exercise():
        started = asyncio.Event()

        async def waiting():
            started.set()
            await asyncio.sleep(10)

        session.status = waiting
        service = SessionService(SimpleNamespace(session=lambda: session), registry, object())
        task = asyncio.create_task(service.execute(Request(Command.STATUS)))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(AgentError) as error:
            await task
        assert error.value.details["reason"] == "canceled"
        assert session.events[-1] == "close"

    run(exercise())


def test_retry_does_not_restart_after_cleanup_consumes_work_budget(selected):
    registry, device = selected
    session = FakeSession(error=AgentError(ErrorCode.NETWORK_ERROR, retryable=True))
    made = []

    async def slow_cleanup(timeout):
        await asyncio.sleep(0.08)

    session.close = slow_cleanup

    def factory():
        made.append(session)
        return session

    service = SessionService(SimpleNamespace(session=factory), registry, object())
    with pytest.raises(AgentError) as error:
        run(service.execute(Request(Command.STATUS, timeout=0.1)))
    assert error.value.code == ErrorCode.TIMEOUT
    assert len(made) == 1


def test_owned_connection_checks_identity_before_loading_secrets(selected, monkeypatch):
    registry, device = selected
    impostor = DiscoveredDevice(
        candidate_id="candidate-other",
        name="test",
        host=device.last_host,
        identifiers={"airplay": "different"},
        pairing={},
    )
    adapter = SimpleNamespace(discover=AsyncMock(return_value=[impostor]))
    vault = SimpleNamespace(get=lambda *args: pytest.fail("Vault accessed before identity matched"))

    async def exercise():
        session = OwnedSession(adapter)
        with pytest.raises(AgentError) as error:
            await session.connect(device, vault, asyncio.get_running_loop().time() + 2)
        assert error.value.code == ErrorCode.IDENTITY_MISMATCH
        await session.close(1)

    run(exercise())


@pytest.mark.parametrize("cancel", [False, True])
def test_partial_facade_connect_keeps_owned_setup_handles(selected, monkeypatch, cancel):
    from ipaddress import IPv4Address

    from pyatv import core
    from pyatv.conf import AppleTV, ManualService
    from pyatv.const import Protocol
    from pyatv.core import facade as facade_module
    from pyatv.support import http

    from apple_tv_agent.models import ProtocolName

    registry, device = selected
    device.paired_protocols = [ProtocolName.AIRPLAY]
    candidate = DiscoveredDevice(
        candidate_id="candidate-test",
        name=device.name,
        host=device.last_host,
        identifiers=device.identifiers,
        pairing={},
    )
    config = AppleTV(IPv4Address(device.last_host), device.name)
    config.add_service(ManualService("test", Protocol.AirPlay, 7000, {}))
    storage = SimpleNamespace(get_settings=AsyncMock(return_value=object()))
    adapter = SimpleNamespace(
        discover=AsyncMock(return_value=[candidate]),
        _identified_config=AsyncMock(return_value=config),
        _memory=AsyncMock(return_value=storage),
    )
    events = []

    class Facade:
        def __init__(self, *args):
            pass

        def takeover(self, *args):
            pass

        def add_protocol(self, setup):
            events.append("setup-retained")

        async def connect(self):
            if cancel:
                raise asyncio.CancelledError
            raise RuntimeError("private-sentinel")

        def close(self):
            return set()  # No protocol was fully connected, as in the upstream facade.

    def close_setup():
        events.append("setup-closed")
        return set()

    setup = core.SetupData(Protocol.AirPlay, AsyncMock(), close_setup, lambda: {}, {}, set())
    monkeypatch.setattr(facade_module, "FacadeAppleTV", Facade)
    monkeypatch.setattr(core, "create_core", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "pyatv.protocols.PROTOCOLS", {Protocol.AirPlay: SimpleNamespace(setup=lambda core: [setup])}
    )
    manager = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(http, "create_session", AsyncMock(return_value=manager))

    async def exercise():
        session = OwnedSession(adapter)
        try:
            with pytest.raises((AgentError, asyncio.CancelledError)):
                await session.connect(
                    device,
                    SimpleNamespace(get=lambda *args: "synthetic"),
                    asyncio.get_running_loop().time() + 2,
                )
        finally:
            await session.close(1)

    run(exercise())
    assert events == ["setup-retained", "setup-closed"]
    manager.close.assert_awaited_once()


@pytest.mark.parametrize(
    "append,replace,expected",
    [
        ("Available", "Unsupported", "available"),
        ("Unsupported", "Available", "unsupported"),
        ("Unavailable", "Available", "unavailable"),
        ("Unknown", "Available", "unknown"),
    ],
)
def test_keyboard_typing_uses_append_capability(append, replace, expected):
    from pyatv.const import KeyboardFocusState

    session = OwnedSession(None)
    session.facade = facade({"TextAppend": append, "TextSet": replace})
    session.facade.keyboard.text_focus_state = KeyboardFocusState.Focused
    result = run(session.capabilities())
    assert result.features[Command.KEYBOARD_TYPE].state == expected
