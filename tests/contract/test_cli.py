import asyncio
import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from apple_tv_agent.cli import main, parse_request
from apple_tv_agent.errors import ERRORS, AgentError, ErrorCode
from apple_tv_agent.models import (
    PAYLOADS,
    ActionData,
    AliasData,
    AppsData,
    CapabilitiesData,
    Command,
    DefaultData,
    DevicesData,
    DiscoveryData,
    DoctorData,
    ForgetData,
    Identifier,
    PairData,
    StatusData,
    failure,
    response_schema,
    success,
)
from apple_tv_agent.ports import CommandResult, Credentials

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas/response-v1.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


class FakeAdapter:
    """Deterministic transport boundary; records requests and never uses the LAN."""

    def __init__(self, data=None, error=None):
        self.data = data if data is not None else DiscoveryData(devices=[])
        self.error = error
        self.requests = []

    async def discover(self, *, host, timeout):
        self.requests.append((host, timeout))
        if self.error:
            raise self.error
        return self.data.devices

    async def execute(self, request, device, credentials):
        self.requests.append(request)
        if self.error:
            raise self.error
        return CommandResult(device_id="test-device", data=self.data)


class FakeService:
    def __init__(self, adapter):
        self.adapter = adapter

    async def execute(self, request):
        if request.command == Command.DISCOVER:
            devices = await self.adapter.discover(host=request.host, timeout=request.timeout)
            return CommandResult(None, DiscoveryData(devices=devices))
        return await self.adapter.execute(request, None, Credentials(values={}))


def invoke(argv, capsys, adapter=None, **kwargs):
    adapter = adapter or FakeAdapter()
    code = main(argv, service_factory=lambda: FakeService(adapter), **kwargs)
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    VALIDATOR.validate(data)
    assert set(data) == {"schema_version", "ok", "command", "device_id", "data", "error"}
    return code, data


def test_generated_schema_is_current():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA == response_schema()
    assert set(PAYLOADS) == set(Command)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["no-such-command"],
        ["remote", "toggle"],
        ["status", "--unknown"],
        ["status", "--time", "5"],
        ["discover", "--host", "::1"],
        ["discover", "--host", "example.com"],
        ["status", "--timeout", "nan"],
        ["--timeout", "inf", "status"],
        ["status", "--timeout", "0"],
        ["status", "--timeout", "121"],
        ["volume", "set", "--level", "-1"],
        ["volume", "set", "--level", "101"],
        ["volume", "set", "--level", "NaN"],
        ["volume", "set", "--level", "Infinity"],
        ["volume", "set"],
        ["apps", "launch"],
        ["devices", "alias"],
        ["keyboard", "type"],
        ["status", "--device", ""],
        ["status", "--device", "\x00"],
        ["status", "--device", "x" * 257],
    ],
)
def test_invalid_input_never_constructs_service(argv, capsys):
    factory = Mock(side_effect=AssertionError("must not access services"))
    assert main(argv, service_factory=factory) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    VALIDATOR.validate(result)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert captured.err == ""
    factory.assert_not_called()


@pytest.mark.parametrize("raw", [b"", b"\xff", b"x" * 4097, "🌍".encode() * 1025])
def test_invalid_text_never_constructs_service(raw, capsys):
    factory = Mock()
    assert (
        main(["keyboard", "type", "--text-stdin"], stdin=io.BytesIO(raw), service_factory=factory)
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    factory.assert_not_called()


def test_unicode_text_is_preserved_and_not_echoed(capsys):
    text = "  Café 🌍 $(not-a-command)\n"
    adapter = FakeAdapter(ActionData(outcome="sent", observed_state=None))
    code, result = invoke(
        ["keyboard", "type", "--text-stdin"], capsys, adapter, stdin=io.BytesIO(text.encode())
    )
    assert code == 0
    assert adapter.requests[0].text == text
    assert text not in repr(adapter.requests[0])
    assert "Café" not in json.dumps(result, ensure_ascii=False)


def test_exact_text_limit_and_timeout_positions():
    request = parse_request(
        [
            "--timeout",
            "10",
            "keyboard",
            "--timeout",
            "20",
            "type",
            "--text-stdin",
            "--timeout",
            "30",
        ],
        io.BytesIO(b"a" * 4096),
    )
    assert len(request.text) == 4096
    assert request.timeout == 30


def test_noninteractive_pairing_never_constructs_service(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    factory = Mock()
    assert main(["pair", "--device", "living-room"], service_factory=factory) == 3
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    assert result["error"]["code"] == "INTERACTIVE_REQUIRED"
    factory.assert_not_called()


@pytest.mark.parametrize(
    "command",
    [
        c
        for c in Command
        if c
        not in {
            Command.DISCOVER,
            Command.DEVICES_LIST,
            Command.DEVICES_ALIAS,
            Command.DEVICES_DEFAULT,
        }
    ],
)
def test_pending_services_are_explicitly_unavailable(command, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    argv = command.value.split(".")
    extra = {
        Command.DEVICES_ALIAS: ["--name", "living-room"],
        Command.VOLUME_SET: ["--level", "50"],
        Command.APPS_LAUNCH: ["--app-id", "com.example.app"],
        Command.KEYBOARD_TYPE: ["--text-stdin"],
    }
    stream = io.BytesIO(b"example") if command == Command.KEYBOARD_TYPE else None
    assert main(argv + extra.get(command, []), stdin=stream) == 4
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    assert result["command"] == command
    assert result["error"]["details"] == {"reason": "not_implemented"}


@pytest.mark.parametrize("code", list(ErrorCode))
def test_all_errors_have_consistent_json_and_exit_mapping(code, capsys):
    status, result = invoke(["status"], capsys, FakeAdapter(error=AgentError(code)))
    assert status == ERRORS[code][0]
    assert result["error"]["code"] == code
    assert result["error"]["retryable"] is False


@pytest.mark.parametrize("error", [RuntimeError("secret-sentinel"), SystemExit("secret-sentinel")])
def test_unknown_exception_is_redacted(capsys, error):
    status, result = invoke(["status"], capsys, FakeAdapter(error=error))
    assert status == 1
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-sentinel" not in json.dumps(result)


def test_invalid_service_payload_is_not_success(capsys):
    status, result = invoke(["status"], capsys, FakeAdapter(DiscoveryData(devices=[])))
    assert status == 1
    assert result["error"]["code"] == "INTERNAL_ERROR"


def test_discovery_success_uses_fake_transport(capsys):
    adapter = FakeAdapter()
    status, result = invoke(["discover", "--host", "192.0.2.5", "--timeout", "3"], capsys, adapter)
    assert status == 0
    assert result["data"] == {"devices": []}
    assert adapter.requests == [("192.0.2.5", 3)]


def test_service_deadline_is_enforced(capsys):
    class SlowService:
        async def execute(self, request):
            await asyncio.sleep(10)

    assert main(["status", "--timeout", "1"], service_factory=SlowService) == 5
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    assert result["error"]["code"] == "TIMEOUT"


def test_schema_rejects_mismatched_data_and_missing_envelope_fields():
    result = failure(Command.STATUS, AgentError(ErrorCode.DEVICE_NOT_FOUND)).model_dump(mode="json")
    result["data"] = {"devices": []}
    assert not VALIDATOR.is_valid(result)
    result["data"] = None
    del result["device_id"]
    assert not VALIDATOR.is_valid(result)


@pytest.mark.parametrize("command", list(Command))
def test_every_success_payload_validates_independently(command):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    status = StatusData(
        observed_at=now,
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
    payloads = {
        DoctorData: DoctorData(version="test", python="3.12", platform="test", checks=[]),
        DiscoveryData: DiscoveryData(devices=[]),
        DevicesData: DevicesData(devices=[], default_device_id=None),
        AliasData: AliasData(aliases=["Living room"]),
        DefaultData: DefaultData(default_device_id="device-id"),
        ForgetData: ForgetData(
            local_credentials_removed=True, registry_removed=True, default_cleared=False
        ),
        PairData: PairData(protocols={}),
        StatusData: status,
        CapabilitiesData: CapabilitiesData(observed_at=now, features={}),
        AppsData: AppsData(apps=[]),
        ActionData: ActionData(outcome="sent", observed_state=None),
    }
    device_id = (
        None
        if command in (Command.DOCTOR, Command.DISCOVER, Command.DEVICES_LIST)
        else "test-device"
    )
    result = success(command, device_id, payloads[PAYLOADS[command]]).model_dump(mode="json")
    VALIDATOR.validate(result)


def test_help_version_and_untrusted_arguments_are_safe(capsys):
    assert main(["--help"]) == 0
    assert "usage:" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert "apple-tv-agent" in capsys.readouterr().out
    assert main(["remote", "secret-sentinel"]) == 2
    captured = capsys.readouterr()
    assert "secret-sentinel" not in captured.out + captured.err


def test_importing_cli_does_not_load_transport_or_vault():
    code = "import sys; import apple_tv_agent.cli; assert 'pyatv' not in sys.modules; assert 'keyring' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_entry_points_match_from_another_directory(tmp_path):
    console = Path(sys.executable).parent / (
        "apple-tv-agent.exe" if os.name == "nt" else "apple-tv-agent"
    )
    commands = [[str(console)], [sys.executable, "-m", "apple_tv_agent"]]
    results = [
        subprocess.run(command + ["status"], cwd=tmp_path, capture_output=True)
        for command in commands
    ]
    assert results[0].stdout == results[1].stdout
    assert [r.returncode for r in results] == [4, 4]
    assert all(r.stderr == b"" for r in results)
    VALIDATOR.validate(json.loads(results[0].stdout))


def test_schema_rejects_unobserved_confirmation_and_missing_action_identity():
    result = success(
        Command.PAUSE, "test-device", ActionData(outcome="sent", observed_state=None)
    ).model_dump(mode="json")
    result["data"]["outcome"] = "confirmed"
    assert not VALIDATOR.is_valid(result)
    result["data"]["outcome"] = "sent"
    result["device_id"] = None
    assert not VALIDATOR.is_valid(result)


@pytest.mark.parametrize(
    "command,data",
    [
        (Command.DOCTOR, DoctorData(version="test", python="3.12", platform="test", checks=[])),
        (Command.DISCOVER, DiscoveryData(devices=[])),
        (Command.DEVICES_LIST, DevicesData(devices=[], default_device_id=None)),
    ],
)
def test_global_success_rejects_device_identity(command, data, capsys):
    with pytest.raises(ValidationError):
        success(command, "stale-device", data)
    envelope = success(command, None, data).model_dump(mode="json")
    envelope["device_id"] = "stale-device"
    assert not VALIDATOR.is_valid(envelope)

    class BadService:
        async def execute(self, request):
            return CommandResult("stale-device", data)

    assert main(command.value.split("."), service_factory=BadService) == 1
    result = json.loads(capsys.readouterr().out)
    VALIDATOR.validate(result)
    assert result["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.parametrize(
    "value", ["", " ", "\u2003", "\t", "id\n", "id\x00x", "id\x7f", "a\tb", "x" * 257]
)
def test_identifier_constraints_match_schema_and_cli(value, capsys):
    adapter = TypeAdapter(Identifier)
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    assert not Draft202012Validator(adapter.json_schema()).is_valid(value)
    factory = Mock()
    assert main(["status", "--device", value], service_factory=factory) == 2
    factory.assert_not_called()
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("value", ["Living room", "Télévision", " 客厅 "])
def test_identifier_preserves_valid_values(value):
    adapter = TypeAdapter(Identifier)
    assert adapter.validate_python(value) == value
    Draft202012Validator(adapter.json_schema()).validate(value)


@pytest.mark.parametrize("actual_tty", [False, True])
@pytest.mark.parametrize("supplied_tty", [False, True])
def test_pairing_uses_supplied_stream(actual_tty, supplied_tty, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: actual_tty)
    stream = Mock()
    stream.isatty.return_value = supplied_tty
    assert main(["pair"], stdin=stream) == (4 if supplied_tty else 3)
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == (
        "FEATURE_UNAVAILABLE" if supplied_tty else "INTERACTIVE_REQUIRED"
    )


@pytest.mark.parametrize("case", ["exit", "output", "stderr", "ok", "fields", "schema", "valid"])
def test_wheel_checks_survive_optimized_python(case):
    script = f"""
import json, runpy
from types import SimpleNamespace
checks = runpy.run_path({str(ROOT / "tools/check_wheel.py")!r})
envelope = dict(schema_version=1, ok=False, command=None, device_id=None, data=None, error={{}})
case = {case!r}
if case == 'ok': envelope['ok'] = True
if case == 'fields': del envelope['data']
results = [SimpleNamespace(returncode=2, stdout=json.dumps(envelope).encode(), stderr=b'') for _ in range(2)]
if case == 'exit': results[0].returncode = 0
if case == 'output': results[0].stdout = b'different'
if case == 'stderr': results[0].stderr = b'unexpected'
checks['check_results'](results, 2)
checks['check_schema']({{'$schema': 'bad' if case == 'schema' else 'https://json-schema.org/draft/2020-12/schema'}})
"""
    result = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True)
    assert (result.returncode == 0) == (case == "valid"), result.stderr
