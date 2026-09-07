"""Pinned pyatv facade ownership and conservative public state normalization."""

import asyncio
from datetime import UTC, datetime
from functools import partial

from pydantic import TypeAdapter, ValidationError

from apple_tv_agent import apps_keyboard
from apple_tv_agent.controls import CORE_CONTROLS, dispatch
from apple_tv_agent.discovery import resolve_identity
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import (
    CapabilitiesData,
    Capability,
    Command,
    Identifier,
    Level,
    Position,
    StatusData,
)
from apple_tv_agent.ports import Credentials

ACTION_FEATURES = {
    **{command: spec[2] for command, spec in CORE_CONTROLS.items()},
    Command.APPS_LIST: "AppList",
    Command.APPS_LAUNCH: "LaunchApp",
    Command.KEYBOARD_TYPE: "TextAppend",
}


def public_error(error):
    from pyatv import exceptions as ex

    if isinstance(error, AgentError):
        return error
    if isinstance(error, (TimeoutError, ex.OperationTimeoutError)):
        return AgentError(ErrorCode.TIMEOUT)
    if isinstance(error, (ex.AuthenticationError, ex.InvalidCredentialsError)):
        return AgentError(ErrorCode.AUTH_FAILED)
    if isinstance(error, ex.NoCredentialsError):
        return AgentError(ErrorCode.PAIRING_REQUIRED)
    if isinstance(error, ex.BackOffError):
        return AgentError(ErrorCode.DEVICE_BUSY)
    if isinstance(error, (OSError, ex.ConnectionFailedError, ex.ConnectionLostError)):
        return AgentError(ErrorCode.NETWORK_ERROR, retryable=True)
    if isinstance(error, (ex.ProtocolError, ex.InvalidResponseError)):
        return AgentError(ErrorCode.NETWORK_ERROR, details={"reason": "invalid_protocol_response"})
    if isinstance(error, (ex.NotSupportedError, ex.NoServiceError)):
        return AgentError(ErrorCode.UNSUPPORTED_FEATURE)
    return AgentError(ErrorCode.INTERNAL_ERROR)


class OwnedSession:
    def __init__(self, adapter):
        self.adapter = adapter
        self.dispatched = False
        self.facade = None
        self.http = None
        self.closers = []

    async def act(self, request):
        try:
            if request.command in apps_keyboard.APP_KEYBOARD_MUTATIONS:
                return await apps_keyboard.dispatch(self, request)
            return await dispatch(self, request)
        except Exception as error:
            raise public_error(error) from None

    async def apps(self):
        try:
            return await apps_keyboard.list_apps(self)
        except Exception as error:
            raise public_error(error) from None

    async def connect(self, device, vault, end):
        try:
            await self._connect(device, vault, end)
        except Exception as error:
            raise public_error(error) from None

    async def _connect(self, device, vault, end):
        from pyatv.const import PairingRequirement
        from pyatv.core import CoreStateDispatcher, create_core
        from pyatv.core.facade import FacadeAppleTV
        from pyatv.protocols import PROTOCOLS
        from pyatv.support.http import create_session

        loop = asyncio.get_running_loop()

        def budget(fraction):
            remaining = end - loop.time()
            if remaining <= 0:
                raise TimeoutError
            return remaining * fraction

        candidates = await self.adapter.discover(host=device.last_host, timeout=budget(0.3))
        if not candidates and device.last_host is not None:
            candidates = await self.adapter.discover(host=None, timeout=budget(0.4))
        candidate = resolve_identity(device, candidates)
        config = await self.adapter._identified_config(device, candidate, budget(0.4))
        values = {
            protocol: vault.get(device.device_id, protocol) for protocol in device.paired_protocols
        }
        if not values or not all(values.values()):
            raise AgentError(ErrorCode.PAIRING_REQUIRED)
        storage = await self.adapter._memory(config, Credentials(values))
        settings = await storage.get_settings(config)
        self.http = await create_session()
        dispatcher = CoreStateDispatcher()
        self.facade = FacadeAppleTV(config, self.http, dispatcher, settings)
        for protocol, methods in PROTOCOLS.items():
            service = config.get_service(protocol)
            if service is None or not service.enabled:
                continue
            if service.pairing == PairingRequirement.Mandatory and not service.credentials:
                continue
            core = await create_core(
                config,
                service,
                settings=settings,
                device_listener=self.facade,
                session_manager=self.http,
                core_dispatcher=dispatcher,
                takeover_method=partial(self.facade.takeover, protocol),
                loop=loop,
            )
            for setup in methods.setup(core):
                # The facade closes only successfully connected protocols; retain all handles.
                close = self._once(setup.close)
                self.closers.append(close)
                self.facade.add_protocol(setup._replace(close=close))
        await self.facade.connect()

    @staticmethod
    def _once(callback):
        called = False

        def close():
            nonlocal called
            if called:
                return set()
            called = True
            return callback()

        return close

    async def close(self, timeout):
        tasks, failed = set(), False
        callbacks = ([self.facade.close] if self.facade is not None else []) + self.closers
        for close in callbacks:
            try:
                tasks.update(close())
            except Exception:
                failed = True
        if self.http is not None:
            tasks.add(asyncio.create_task(self.http.close()))
        if tasks:
            try:
                async with asyncio.timeout(timeout):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                failed = failed or any(isinstance(result, BaseException) for result in results)
            except TimeoutError:
                raise AgentError(ErrorCode.TIMEOUT, details={"reason": "cleanup_timeout"}) from None
        if failed:
            raise AgentError(ErrorCode.NETWORK_ERROR, details={"reason": "cleanup_failed"})

    def feature(self, name):
        from pyatv.const import FeatureName

        try:
            state = self.facade.features.get_feature(FeatureName[name]).state.name.lower()
            if state not in ("available", "unavailable", "unsupported", "unknown"):
                state = "unknown"
        except Exception:
            state = "unknown"
        return Capability(state=state, reason=None if state == "available" else state)

    async def capabilities(self):
        features = {command: self.feature(feature) for command, feature in ACTION_FEATURES.items()}
        if (
            features[Command.APPS_LAUNCH].state == "available"
            and features[Command.APPS_LIST].state != "available"
        ):
            features[Command.APPS_LAUNCH] = Capability(
                state=features[Command.APPS_LIST].state, reason="app_list_required"
            )
        if features[Command.KEYBOARD_TYPE].state == "available":
            focus = self._focus()
            if focus != "focused":
                features[Command.KEYBOARD_TYPE] = Capability(
                    state="unavailable", reason="keyboard_not_focused"
                )
        return CapabilitiesData(observed_at=datetime.now(UTC), features=features)

    def _focus(self):
        if self.feature("TextFocusState").state != "available":
            return "unknown"
        try:
            value = self.facade.keyboard.text_focus_state.name.lower()
            return value if value in ("focused", "unfocused") else "unknown"
        except Exception:
            return "unknown"

    async def status(self):
        from pyatv.exceptions import NotSupportedError

        reasons = {}
        playing = None
        metadata_reason = "not_reported"
        try:
            playing = await self.facade.metadata.playing()
        except NotSupportedError:
            metadata_reason = "unsupported"
            reasons["playback_state"] = metadata_reason
        except Exception as error:
            raise public_error(error) from None

        def read(field, feature, getter, validator=None):
            availability = self.feature(feature) if feature else None
            if availability is not None and availability.state != "available":
                reasons[field] = availability.state
                return None
            try:
                value = getter()
                if value is None:
                    reasons[field] = "not_reported"
                    return None
                return (
                    TypeAdapter(validator).validate_python(value, strict=True)
                    if validator
                    else value
                )
            except NotSupportedError:
                reasons[field] = "unsupported"
            except (ValidationError, ValueError, AttributeError):
                reasons[field] = "invalid_or_missing_value"
            except Exception as error:
                raise public_error(error) from None
            return None

        data = {}
        for field, feature, prop, validator in (
            ("title", "Title", "title", str),
            ("artist", "Artist", "artist", str),
            ("album", "Album", "album", str),
            ("position", "Position", "position", Position),
            ("duration", "TotalTime", "total_time", Position),
        ):
            if playing is None:
                data[field] = None
                reasons[field] = self.feature(feature).reason or metadata_reason
            else:
                data[field] = read(
                    field, feature, lambda prop=prop: getattr(playing, prop), validator
                )
        state = (
            read("playback_state", None, lambda: playing.device_state.name.lower())
            if playing
            else None
        )
        state = "idle" if state == "nomedia" else state
        if state not in ("playing", "paused", "stopped", "loading", "seeking", "idle"):
            reasons.setdefault("playback_state", metadata_reason if playing is None else "unknown")
            state = None
        power = read("power", "PowerState", lambda: self.facade.power.power_state.name.lower())
        if power not in ("on", "off"):
            reasons.setdefault("power", "unknown")
            power = None
        app_id = read(
            "app_id",
            "App",
            lambda: self.facade.metadata.app.identifier if self.facade.metadata.app else None,
            Identifier,
        )
        volume = read("volume", "Volume", lambda: self.facade.audio.volume, Level)
        focus = self._focus()
        if focus == "unknown":
            reasons["keyboard_focus"] = self.feature("TextFocusState").reason or "unknown"
        return StatusData(
            observed_at=datetime.now(UTC),
            playback_state=state,
            power=power,
            app_id=app_id,
            volume=volume,
            keyboard_focus=focus,
            unavailable_fields=reasons,
            **data,
        )
