"""Typed v1 payloads and generated success/failure envelope schema."""

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    TypeAdapter,
    create_model,
    model_validator,
)

from apple_tv_agent.errors import ERRORS, AgentError, ErrorCode

Identifier = Annotated[str, Field(min_length=1, max_length=256)]
Level = Annotated[FiniteFloat, Field(ge=0, le=100)]
Position = Annotated[FiniteFloat, Field(ge=0)]


class Command(StrEnum):
    DOCTOR = "doctor"
    DISCOVER = "discover"
    DEVICES_LIST = "devices.list"
    DEVICES_ALIAS = "devices.alias"
    DEVICES_DEFAULT = "devices.default"
    DEVICES_FORGET = "devices.forget"
    PAIR = "pair"
    STATUS = "status"
    CAPABILITIES = "capabilities"
    UP = "remote.up"
    DOWN = "remote.down"
    LEFT = "remote.left"
    RIGHT = "remote.right"
    SELECT = "remote.select"
    MENU = "remote.menu"
    HOME = "remote.home"
    PLAY = "remote.play"
    PAUSE = "remote.pause"
    STOP = "remote.stop"
    NEXT = "remote.next"
    PREVIOUS = "remote.previous"
    POWER_ON = "power.on"
    POWER_OFF = "power.off"
    VOLUME_UP = "volume.up"
    VOLUME_DOWN = "volume.down"
    VOLUME_SET = "volume.set"
    APPS_LIST = "apps.list"
    APPS_LAUNCH = "apps.launch"
    KEYBOARD_TYPE = "keyboard.type"


class ProtocolName(StrEnum):
    AIRPLAY = "airplay"
    COMPANION = "companion"
    MRP = "mrp"
    RAOP = "raop"
    DMAP = "dmap"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Capability(Model):
    state: Literal["available", "unavailable", "unsupported", "unknown"]
    reason: str | None


class DiscoveredDevice(Model):
    candidate_id: Identifier
    name: str
    host: str
    identifiers: dict[ProtocolName, Identifier]
    pairing: dict[
        ProtocolName, Literal["mandatory", "optional", "not_needed", "disabled", "unsupported"]
    ]


class DeviceRecord(Model):
    device_id: Identifier
    name: str
    aliases: list[Identifier]
    identifiers: dict[ProtocolName, Identifier]
    last_host: str | None
    paired_protocols: list[ProtocolName]


class DiscoveryData(Model):
    devices: list[DiscoveredDevice]


class DevicesData(Model):
    devices: list[DeviceRecord]
    default_device_id: Identifier | None


class AliasData(Model):
    aliases: list[Identifier]


class DefaultData(Model):
    default_device_id: Identifier


class ForgetData(Model):
    local_credentials_removed: bool
    registry_removed: bool
    default_cleared: bool


class PairData(Model):
    protocols: dict[ProtocolName, Literal["paired", "not_needed", "failed"]]


class StatusData(Model):
    observed_at: AwareDatetime
    playback_state: Literal["playing", "paused", "stopped", "loading", "seeking", "idle"] | None
    power: Literal["on", "off"] | None
    title: str | None
    artist: str | None
    album: str | None
    app_id: Identifier | None
    position: Position | None
    duration: Position | None
    volume: Level | None
    keyboard_focus: Literal["focused", "unfocused", "unknown"]
    unavailable_fields: dict[str, str]


class CapabilitiesData(Model):
    observed_at: AwareDatetime
    features: dict[Command, Capability]


class ActionData(Model):
    model_config = ConfigDict(
        json_schema_extra={
            "if": {"properties": {"outcome": {"const": "confirmed"}}},
            "then": {"properties": {"observed_state": {"not": {"type": "null"}}}},
        }
    )

    outcome: Literal["confirmed", "sent", "unknown"]
    observed_state: StatusData | None

    @model_validator(mode="after")
    def require_confirmation_observation(self):
        if self.outcome == "confirmed" and self.observed_state is None:
            raise ValueError("Confirmed outcomes require an observation.")
        return self


class App(Model):
    app_id: Identifier
    name: str


class AppsData(Model):
    apps: list[App]


class Check(Model):
    name: str
    status: Literal["pass", "fail", "not_tested"]
    message: str


class DoctorData(Model):
    version: str
    python: str
    platform: str
    checks: list[Check]


PAYLOADS = {
    Command.DOCTOR: DoctorData,
    Command.DISCOVER: DiscoveryData,
    Command.DEVICES_LIST: DevicesData,
    Command.DEVICES_ALIAS: AliasData,
    Command.DEVICES_DEFAULT: DefaultData,
    Command.DEVICES_FORGET: ForgetData,
    Command.PAIR: PairData,
    Command.STATUS: StatusData,
    Command.CAPABILITIES: CapabilitiesData,
    Command.APPS_LIST: AppsData,
    **{
        command: ActionData
        for command in Command
        if command.value.startswith(("remote.", "power.", "volume."))
    },
    Command.APPS_LAUNCH: ActionData,
    Command.KEYBOARD_TYPE: ActionData,
}


class ErrorData(Model):
    code: ErrorCode
    message: str
    retryable: bool
    details: dict[str, JsonValue]


class Envelope(Model):
    schema_version: Literal[1]
    device_id: Identifier | None


class Failure(Envelope):
    ok: Literal[False]
    command: Command | None
    data: None
    error: ErrorData


SUCCESS_MODELS = {
    command: create_model(
        command.value.replace(".", "_").title().replace("_", "") + "Success",
        __base__=Envelope,
        device_id=(
            Identifier | None
            if command in (Command.DOCTOR, Command.DISCOVER, Command.DEVICES_LIST)
            else Identifier,
            ...,
        ),
        ok=(Literal[True], ...),
        command=(Literal[command.value], ...),
        data=(payload, ...),
        error=(type(None), ...),
    )
    for command, payload in PAYLOADS.items()
}
RESPONSE_ADAPTER = TypeAdapter(Union[tuple(SUCCESS_MODELS.values()) + (Failure,)])


def success(command: Command, device_id: str | None, data: Model) -> Model:
    return SUCCESS_MODELS[command](
        schema_version=1,
        ok=True,
        command=command.value,
        device_id=device_id,
        data=data,
        error=None,
    )


def failure(command: Command | None, error: AgentError) -> Failure:
    # Until a service has resolved identity, never report an input alias as a device ID.
    return Failure(
        schema_version=1,
        ok=False,
        command=command,
        device_id=None,
        data=None,
        error=ErrorData(
            code=error.code,
            message=ERRORS[error.code][1],
            retryable=error.retryable,
            details=error.details,
        ),
    )


def response_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/qwts/apple-tv-agent/blob/main/schemas/response-v1.json",
        **RESPONSE_ADAPTER.json_schema(),
    }
