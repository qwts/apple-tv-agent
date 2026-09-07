"""Allowlisted core controls and conservative matching of observed results."""

import math

from apple_tv_agent.apps_keyboard import APP_KEYBOARD_MUTATIONS
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import ActionData, Command

CORE_CONTROLS = {
    Command.UP: ("remote_control", "up", "Up"),
    Command.DOWN: ("remote_control", "down", "Down"),
    Command.LEFT: ("remote_control", "left", "Left"),
    Command.RIGHT: ("remote_control", "right", "Right"),
    Command.SELECT: ("remote_control", "select", "Select"),
    Command.MENU: ("remote_control", "menu", "Menu"),
    Command.HOME: ("remote_control", "home", "Home"),
    Command.PLAY: ("remote_control", "play", "Play"),
    Command.PAUSE: ("remote_control", "pause", "Pause"),
    Command.STOP: ("remote_control", "stop", "Stop"),
    Command.NEXT: ("remote_control", "next", "Next"),
    Command.PREVIOUS: ("remote_control", "previous", "Previous"),
    Command.POWER_ON: ("power", "turn_on", "TurnOn"),
    Command.POWER_OFF: ("power", "turn_off", "TurnOff"),
    Command.VOLUME_UP: ("audio", "volume_up", "VolumeUp"),
    Command.VOLUME_DOWN: ("audio", "volume_down", "VolumeDown"),
    Command.VOLUME_SET: ("audio", "set_volume", "SetVolume"),
}

MUTATIONS = set(CORE_CONTROLS) | APP_KEYBOARD_MUTATIONS

PLAYBACK_TARGETS = {Command.PLAY: "playing", Command.PAUSE: "paused", Command.STOP: "stopped"}
POWER_TARGETS = {Command.POWER_ON: "on", Command.POWER_OFF: "off"}
VOLUME_COMMANDS = {Command.VOLUME_UP, Command.VOLUME_DOWN, Command.VOLUME_SET}


def confirmed(request, observed, before):
    if request.command in PLAYBACK_TARGETS:
        return observed.playback_state == PLAYBACK_TARGETS[request.command]
    if request.command in POWER_TARGETS:
        return observed.power == POWER_TARGETS[request.command]
    if observed.volume is None:
        return False
    if request.command == Command.VOLUME_SET:
        return math.isclose(observed.volume, request.level, rel_tol=0, abs_tol=0.01)
    if before is None or before.volume is None:
        return False
    if request.command == Command.VOLUME_UP:
        return observed.volume > before.volume
    if request.command == Command.VOLUME_DOWN:
        return observed.volume < before.volume
    return False


async def dispatch(session, request):
    if request.command not in CORE_CONTROLS:
        raise AgentError(ErrorCode.FEATURE_UNAVAILABLE)
    interface, method, feature = CORE_CONTROLS[request.command]
    availability = session.feature(feature)
    if availability.state != "available":
        code = (
            ErrorCode.UNSUPPORTED_FEATURE
            if availability.state == "unsupported"
            else ErrorCode.FEATURE_UNAVAILABLE
        )
        raise AgentError(code, details={"feature": feature, "state": availability.state})
    kwargs = {}
    if request.command == Command.VOLUME_SET:
        if (
            request.level is None
            or not math.isfinite(request.level)
            or not 0 <= request.level <= 100
        ):
            raise AgentError(ErrorCode.INVALID_ARGUMENT)
        kwargs["level"] = request.level
    if request.command in POWER_TARGETS:
        kwargs["await_new_state"] = False
    before = None
    if (
        request.command in (Command.VOLUME_UP, Command.VOLUME_DOWN)
        and session.feature("Volume").state == "available"
    ):
        before = await session.status()
    operation = getattr(getattr(session.facade, interface), method)
    # No retry is permitted after this boundary, even when the library raises immediately.
    session.dispatched = True
    await operation(**kwargs)
    if (
        request.command in PLAYBACK_TARGETS
        or request.command in POWER_TARGETS
        or request.command in VOLUME_COMMANDS
    ):
        observed = await session.status()
        return ActionData(
            outcome="confirmed" if confirmed(request, observed, before) else "sent",
            observed_state=observed,
        )
    return ActionData(outcome="sent", observed_state=None)
