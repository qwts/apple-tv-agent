import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from apple_tv_agent.cli import main
from apple_tv_agent.diagnostics import DoctorService
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Command
from apple_tv_agent.registry import DeviceRegistry
from apple_tv_agent.request import Request


def run(coro):
    return asyncio.run(coro)


def service(**overrides):
    args = dict(
        registry_factory=lambda: SimpleNamespace(
            snapshot=AsyncMock(return_value=SimpleNamespace(devices=[]))
        ),
        vault_factory=Mock(return_value=object()),
        adapter_factory=Mock(side_effect=AssertionError("network must be opt-in")),
        version=lambda name: "1.2.3",
        import_module=lambda name: object(),
    )
    return DoctorService(**(args | overrides))


def checks(result):
    return {check.name: check for check in result.data.checks}


def test_default_never_constructs_network_or_accesses_credentials():
    vault = Mock()
    adapter_factory = Mock()
    result = run(
        service(vault_factory=lambda: vault, adapter_factory=adapter_factory).execute(
            Request(Command.DOCTOR)
        )
    )
    assert result.device_id is None
    adapter_factory.assert_not_called()
    assert vault.mock_calls == []
    report = checks(result)
    assert report["network"].status == "not_tested"
    assert report["vault_access"].status == "not_tested"
    assert report["native_backend"].status == "pass"


@pytest.mark.parametrize(
    "error", [ImportError("private-sentinel"), RuntimeError("private-sentinel")]
)
def test_broken_dependencies_do_not_leak_exception(error):
    result = run(service(import_module=Mock(side_effect=error)).execute(Request(Command.DOCTOR)))
    assert checks(result)["dependency_pyatv"].status == "fail"
    assert "private-sentinel" not in result.data.model_dump_json()


def test_missing_distribution_is_actionable():
    from importlib.metadata import PackageNotFoundError

    result = run(
        service(version=Mock(side_effect=PackageNotFoundError("private-sentinel"))).execute(
            Request(Command.DOCTOR)
        )
    )
    check = checks(result)["dependency_pyatv"]
    assert check.status == "fail" and "Reinstall" in check.message
    assert "private-sentinel" not in result.data.model_dump_json()


@pytest.mark.parametrize(
    "error",
    [
        AgentError(ErrorCode.CREDENTIAL_STORE_UNAVAILABLE, details={"secret": "private-sentinel"}),
        RuntimeError("private-sentinel"),
    ],
)
def test_vault_failure_does_not_claim_unlocked_or_echo_details(error):
    result = run(service(vault_factory=Mock(side_effect=error)).execute(Request(Command.DOCTOR)))
    assert checks(result)["native_backend"].status == "fail"
    assert checks(result)["vault_access"].status == "not_tested"
    assert "private-sentinel" not in result.data.model_dump_json()


def test_corrupt_registry_is_preserved_and_redacted(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("private-sentinel", encoding="utf-8")
    result = run(
        service(registry_factory=lambda: DeviceRegistry(path)).execute(Request(Command.DOCTOR))
    )
    assert checks(result)["registry"].status == "fail"
    assert path.read_text() == "private-sentinel"
    assert "private-sentinel" not in result.data.model_dump_json()


@pytest.mark.parametrize("devices,expected", [([], "not_tested"), ([object()], "pass")])
def test_network_reports_observations_only(devices, expected):
    adapter = SimpleNamespace(discover=AsyncMock(return_value=devices))
    result = run(
        service(adapter_factory=lambda: adapter).execute(Request(Command.DOCTOR, network=True))
    )
    report = checks(result)["network"]
    assert report.status == expected
    assert adapter.discover.await_count == 1
    assert adapter.discover.call_args.kwargs["host"] is None
    assert 0 < adapter.discover.call_args.kwargs["timeout"] <= 15
    if not devices:
        assert "does not establish a firewall failure" in report.message


def test_network_timeout_is_bounded_observation():
    async def slow(**kwargs):
        await asyncio.sleep(10)

    result = run(
        service(adapter_factory=lambda: SimpleNamespace(discover=slow)).execute(
            Request(Command.DOCTOR, network=True, timeout=0.05)
        )
    )
    assert checks(result)["network"].status == "fail"
    assert "time budget" in checks(result)["network"].message


def test_network_exception_redaction():
    adapter = SimpleNamespace(discover=AsyncMock(side_effect=OSError("private-sentinel")))
    result = run(
        service(adapter_factory=lambda: adapter).execute(Request(Command.DOCTOR, network=True))
    )
    assert checks(result)["network"].status == "fail"
    assert "private-sentinel" not in result.data.model_dump_json()


def test_cli_completed_report_can_contain_failed_checks(capsys):
    diagnostic = service(vault_factory=Mock(side_effect=RuntimeError("private-sentinel")))
    assert main(["doctor"], service_factory=lambda: diagnostic) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["ok"] is True and report["device_id"] is None
    assert any(check["status"] == "fail" for check in report["data"]["checks"])
    assert "private-sentinel" not in output.out + output.err
    assert output.err == ""
