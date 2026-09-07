"""Exact installed-app selection and focused, verbatim keyboard append."""

from pydantic import ValidationError

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import ActionData, App, AppsData, Command

APP_KEYBOARD_MUTATIONS = {Command.APPS_LAUNCH, Command.KEYBOARD_TYPE}


def require(session, feature):
    availability = session.feature(feature)
    if availability.state != "available":
        raise AgentError(
            ErrorCode.UNSUPPORTED_FEATURE
            if availability.state == "unsupported"
            else ErrorCode.FEATURE_UNAVAILABLE,
            details={"feature": feature, "state": availability.state},
        )


async def list_apps(session):
    require(session, "AppList")
    apps = await session.facade.apps.app_list()
    try:
        return AppsData(apps=[App(app_id=app.identifier, name=app.name) for app in apps])
    except (ValidationError, AttributeError, TypeError):
        raise AgentError(ErrorCode.NETWORK_ERROR, details={"reason": "invalid_app_list"}) from None


async def dispatch(session, request):
    if request.command == Command.APPS_LAUNCH:
        app_id = request.app_id
        if not app_id:
            raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "app_id_required"})
        if any(char in app_id for char in (":", "/", "\\")):
            raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "invalid_app_id"})
        require(session, "LaunchApp")
        installed = await list_apps(session)
        if app_id not in {app.app_id for app in installed.apps}:
            raise AgentError(
                ErrorCode.INVALID_ARGUMENT,
                details={
                    "reason": "app_not_installed",
                    "recovery": "Run apps list and use an exact app_id.",
                },
            )
        # Refresh after the awaited list operation; do not use cached capabilities.
        require(session, "LaunchApp")
        operation = session.facade.apps.launch_app
        argument = app_id
    elif request.command == Command.KEYBOARD_TYPE:
        text = request.text
        try:
            valid = isinstance(text, str) and 1 <= len(text.encode("utf-8")) <= 4096
        except UnicodeError:
            valid = False
        if not valid:
            raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "invalid_text_input"})
        require(session, "TextAppend")
        if session._focus() != "focused":
            raise AgentError(
                ErrorCode.FEATURE_UNAVAILABLE, details={"reason": "keyboard_not_focused"}
            )
        operation = session.facade.keyboard.text_append
        argument = text
    else:
        raise AgentError(ErrorCode.FEATURE_UNAVAILABLE)
    session.dispatched = True
    await operation(argument)
    # Never retrieve input text or mistake playing-app metadata for foreground UI state.
    return ActionData(outcome="sent", observed_state=None)
