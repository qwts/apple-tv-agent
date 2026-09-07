import asyncio
import json
import multiprocessing
from ipaddress import IPv4Address
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from filelock import FileLock
from pyatv.const import OperatingSystem, PairingRequirement, Protocol

from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter, normalize
from apple_tv_agent.cli import main
from apple_tv_agent.discovery import resolve_identity, select_device, select_pairing_candidate
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import DiscoveredDevice
from apple_tv_agent.registry import DeviceRegistry
from apple_tv_agent.service import ContractService


def candidate(identity="one", host="192.0.2.1", **extra):
    return DiscoveredDevice(
        candidate_id="candidate-" + identity,
        name="Entertainment Room",
        host=host,
        identifiers={"airplay": identity, **extra},
        pairing={},
    )


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def registry(tmp_path):
    return DeviceRegistry(tmp_path / "config with spaces" / "registry.json")


def test_registry_registration_is_explicit_and_preserves_defaults(registry):
    assert run(registry.snapshot()).devices == []
    assert not registry.path.exists()
    first = run(registry.register(candidate()))
    assert first.paired_protocols == []
    assert run(registry.snapshot()).default_device_id is None
    run(registry.alias(first.device_id, "Living room"))
    run(registry.set_default("Living room"))
    moved = run(registry.register(candidate(host="192.0.2.8", companion="two")))
    assert moved.device_id == first.device_id
    assert moved.aliases == ["Living room"]
    assert moved.last_host == "192.0.2.8"
    snapshot = run(DeviceRegistry(registry.path).snapshot())
    assert snapshot.default_device_id == first.device_id
    assert len(snapshot.devices) == 1
    assert moved.identifiers == {"airplay": "one", "companion": "two"}
    assert set(json.loads(registry.path.read_text())) == {
        "schema_version",
        "devices",
        "default_device_id",
    }


def test_selection_never_uses_name_or_falls_back(registry):
    first = run(registry.register(candidate()))
    assert select_device([first], None, None) == first
    second = run(registry.register(candidate("second", "192.0.2.2")))
    devices = [first, second]
    with pytest.raises(AgentError) as error:
        select_device(devices, None, None)
    assert error.value.code == ErrorCode.DEVICE_AMBIGUOUS
    assert len(error.value.details["candidates"]) == 2
    for explicit in ("invalid", "Entertainment Room"):
        with pytest.raises(AgentError) as error:
            select_device(devices, first.device_id, explicit)
        assert error.value.code == ErrorCode.DEVICE_NOT_FOUND
    assert select_device(devices, first.device_id, second.device_id) == second
    assert select_device(devices, first.device_id, None) == first
    with pytest.raises(AgentError) as error:
        select_device([], None, None)
    assert error.value.code == ErrorCode.DEVICE_NOT_FOUND


def test_alias_collision_and_uuid_shadowing_are_rejected(registry):
    first = run(registry.register(candidate()))
    second = run(registry.register(candidate("second")))
    run(registry.alias(first.device_id, "客厅"))
    run(registry.alias(first.device_id, "客厅"))
    for owner, name in [
        (second.device_id, "客厅"),
        (first.device_id, second.device_id),
        (first.device_id, first.device_id),
    ]:
        with pytest.raises(AgentError) as error:
            run(registry.alias(owner, name))
        assert error.value.details["reason"] == "alias_in_use"
    assert run(registry.snapshot()).devices[0].aliases == ["客厅"]


def test_identity_checks_dhcp_reuse_and_conflicting_protocols(registry):
    device = run(registry.register(candidate(companion="companion-one")))
    moved = candidate(host="192.0.2.8")
    assert resolve_identity(device, [candidate("different"), moved]) == moved
    for scan in (
        [candidate("different")],
        [candidate(companion="wrong")],
        [candidate(), candidate(host="192.0.2.9")],
    ):
        with pytest.raises(AgentError) as error:
            resolve_identity(device, scan)
        assert error.value.code == ErrorCode.IDENTITY_MISMATCH
    with pytest.raises(AgentError) as error:
        resolve_identity(device, [])
    assert error.value.code == ErrorCode.DEVICE_NOT_FOUND
    with pytest.raises(AgentError) as error:
        run(registry.register(candidate(companion="wrong")))
    assert error.value.code == ErrorCode.IDENTITY_MISMATCH
    assert run(registry.snapshot()).devices == [device]


def test_registration_rejects_bridging_two_registered_identities(registry):
    run(registry.register(candidate()))
    other = candidate("other")
    other.identifiers = {"companion": "two"}
    run(registry.register(other))
    with pytest.raises(AgentError) as error:
        run(registry.register(candidate(companion="two")))
    assert error.value.code == ErrorCode.IDENTITY_MISMATCH


def test_unregistered_pairing_requires_explicit_candidate(registry):
    discovered = candidate()
    with pytest.raises(AgentError):
        select_pairing_candidate([], None, [discovered], None)
    assert select_pairing_candidate([], None, [discovered], discovered.candidate_id) == discovered
    with pytest.raises(AgentError):
        select_pairing_candidate([], None, [discovered], discovered.name)
    registered = run(registry.register(discovered))
    assert (
        select_pairing_candidate([registered], registered.device_id, [discovered], None)
        == discovered
    )
    with pytest.raises(AgentError):
        select_pairing_candidate([registered], registered.device_id, [discovered], "typo")


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        '{"schema_version":2}',
        '{"schema_version":true}',
        '{"schema_version":1}',
        '{"schema_version":1,"devices":[],"default_device_id":"missing"}',
    ],
)
def test_corrupt_registry_is_preserved_with_recovery_hint(registry, raw):
    registry.path.parent.mkdir(parents=True)
    registry.path.write_text(raw)
    with pytest.raises(AgentError) as error:
        run(registry.register(candidate()))
    assert error.value.code == ErrorCode.CONFIG_ERROR
    assert "recovery" in error.value.details
    assert registry.path.read_text() == raw


@pytest.mark.parametrize("damage", ["uuid", "alias", "identity", "extra"])
def test_invalid_registry_records_are_rejected(registry, damage):
    run(registry.register(candidate()))
    data = json.loads(registry.path.read_text())
    if damage == "uuid":
        data["devices"][0]["device_id"] = "not-a-uuid"
    if damage == "alias":
        data["devices"][0]["aliases"] = ["same", "same"]
    if damage == "identity":
        data["devices"][0]["identifiers"] = {}
    if damage == "extra":
        data["credentials"] = "secret-sentinel"
    raw = json.dumps(data)
    registry.path.write_text(raw)
    with pytest.raises(AgentError) as error:
        run(registry.snapshot())
    assert error.value.code == ErrorCode.CONFIG_ERROR
    assert error.value.details["reason"] == "invalid_registry"
    assert "secret-sentinel" not in str(error.value.details)
    assert registry.path.read_text() == raw


def test_failed_replace_retains_old_registry_and_cleans_temporary(registry, monkeypatch):
    device = run(registry.register(candidate()))
    original = registry.path.read_bytes()

    def fail(*args):
        raise PermissionError("secret-sentinel")

    monkeypatch.setattr("apple_tv_agent.registry.os.replace", fail)
    with pytest.raises(AgentError) as error:
        run(registry.alias(device.device_id, "new"))
    assert error.value.code == ErrorCode.CONFIG_ERROR
    assert error.value.details["reason"] == "registry_io"
    assert registry.path.read_bytes() == original
    assert list(registry.path.parent.glob(".registry-*.tmp")) == []


def add_alias(path, device_id, name):
    run(DeviceRegistry(path).alias(device_id, name))


def test_concurrent_process_updates_do_not_lose_aliases(registry):
    device = run(registry.register(candidate()))
    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(target=add_alias, args=(registry.path, device.device_id, f"alias-{i}"))
        for i in range(4)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        if worker.is_alive():
            worker.terminate()
            worker.join()
            pytest.fail("Registry writer did not finish")
        assert worker.exitcode == 0
    assert set(run(registry.snapshot()).devices[0].aliases) == {f"alias-{i}" for i in range(4)}


def test_lock_is_bounded_and_wait_is_cancellable(registry):
    run(registry.register(candidate()))
    with FileLock(str(registry.path) + ".lock"):
        registry.timeout = 0.05
        with pytest.raises(AgentError) as error:
            run(registry.snapshot())
        assert error.value.code == ErrorCode.DEVICE_BUSY

        async def cancel():
            registry.timeout = 5
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    await registry.snapshot()

        run(cancel())
    assert len(run(registry.snapshot()).devices) == 1


def config(identity="one", host="192.0.2.1", requirement=PairingRequirement.Mandatory):
    return SimpleNamespace(
        name="Entertainment Room",
        device_info=SimpleNamespace(operating_system=OperatingSystem.TvOS),
        address=IPv4Address(host),
        services=[
            SimpleNamespace(protocol=Protocol.AirPlay, identifier=identity, pairing=requirement)
        ],
    )


@pytest.mark.parametrize("requirement", list(PairingRequirement))
def test_normalize_pairing_and_identity_stable_across_dhcp(requirement):
    first = normalize(config(requirement=requirement))
    moved = normalize(config(host="192.0.2.9", requirement=requirement))
    assert first.candidate_id == moved.candidate_id
    assert first.host != moved.host
    assert first.identifiers == {"airplay": "one"}


def test_adapter_calls_scan_without_connections_or_storage(monkeypatch):
    import pyatv

    scan = AsyncMock(return_value=[config()])
    monkeypatch.setattr(pyatv, "scan", scan)
    monkeypatch.setattr(pyatv, "connect", AsyncMock(side_effect=AssertionError("No connection")))
    result = run(PyatvAdapter().discover(host="192.0.2.1", timeout=2))
    assert result[0].host == "192.0.2.1"
    assert scan.call_args.kwargs["hosts"] == ["192.0.2.1"]
    assert 0 < scan.call_args.kwargs["timeout"] < 2
    scan.return_value = []
    assert run(PyatvAdapter().discover(host=None, timeout=2)) == []
    assert scan.call_args.kwargs["hosts"] is None
    with pytest.raises(AgentError) as error:
        run(PyatvAdapter().discover(host="::1", timeout=2))
    assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_adapter_timeout_cancels_scan(monkeypatch):
    import pyatv

    closed = []

    async def slow(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            closed.append(True)

    monkeypatch.setattr(pyatv, "scan", slow)
    with pytest.raises(TimeoutError):
        run(PyatvAdapter().discover(host=None, timeout=0.02))
    assert closed == [True]


def test_discovery_and_registry_service_are_isolated(registry, capsys):
    adapter = SimpleNamespace(discover=AsyncMock(return_value=[candidate()]))
    service = ContractService(adapter=adapter, registry=registry)
    assert main(["discover"], service_factory=lambda: service) == 0
    assert (
        json.loads(capsys.readouterr().out)["data"]["devices"][0]["candidate_id"] == "candidate-one"
    )
    assert not registry.path.exists()
    device = run(registry.register(candidate()))
    for argv in (
        ["devices", "alias", "--name", "living"],
        ["devices", "default"],
        ["devices", "list"],
    ):
        assert main(argv, service_factory=lambda: service) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["ok"] is True
    assert result["data"]["default_device_id"] == device.device_id
    assert adapter.discover.await_count == 1


def alias_with_result(path, device_id, queue):
    try:
        run(DeviceRegistry(path).alias(device_id, "shared"))
        queue.put("ok")
    except AgentError as error:
        queue.put(error.code.value)


def test_concurrent_alias_collision_has_one_winner(registry):
    first = run(registry.register(candidate()))
    second = run(registry.register(candidate("two")))
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [
        context.Process(target=alias_with_result, args=(registry.path, d.device_id, queue))
        for d in (first, second)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    assert sorted([queue.get(timeout=2), queue.get(timeout=2)]) == ["INVALID_ARGUMENT", "ok"]
    assert sum("shared" in d.aliases for d in run(registry.snapshot()).devices) == 1
    queue.close()


def crash_before_replace(path, device_id):
    import os

    import apple_tv_agent.registry as module

    module.os.replace = lambda *args: os._exit(17)
    run(DeviceRegistry(path).alias(device_id, "never-committed"))


def test_process_interruption_preserves_file_and_releases_lock(registry):
    device = run(registry.register(candidate()))
    original = registry.path.read_bytes()
    worker = multiprocessing.get_context("spawn").Process(
        target=crash_before_replace, args=(registry.path, device.device_id)
    )
    worker.start()
    worker.join(20)
    assert worker.exitcode == 17
    assert registry.path.read_bytes() == original
    run(registry.alias(device.device_id, "after-crash"))
    assert run(registry.snapshot()).devices[0].aliases == ["after-crash"]


def test_duplicate_json_keys_are_not_silently_discarded(registry):
    registry.path.parent.mkdir(parents=True)
    raw = '{"schema_version":2,"schema_version":1,"devices":[],"default_device_id":null}'
    registry.path.write_text(raw)
    with pytest.raises(AgentError):
        run(registry.snapshot())
    assert registry.path.read_text() == raw


def test_discovery_excludes_non_tvos_devices(monkeypatch):
    import pyatv

    other = config("speaker")
    other.device_info.operating_system = OperatingSystem.Unknown
    monkeypatch.setattr(pyatv, "scan", AsyncMock(return_value=[other, config()]))
    result = run(PyatvAdapter().discover(host=None, timeout=2))
    assert len(result) == 1
    assert result[0].identifiers == {"airplay": "one"}


@pytest.mark.parametrize("alias", ["candidate-", "candidate-one", "candidate-" + "a" * 64])
def test_candidate_namespace_cannot_be_shadowed_by_alias(registry, alias):
    device = run(registry.register(candidate()))
    original = registry.path.read_bytes()
    with pytest.raises(AgentError) as error:
        run(registry.alias(device.device_id, alias))
    assert error.value.code == ErrorCode.INVALID_ARGUMENT
    assert error.value.details["reason"] == "reserved_alias"
    assert registry.path.read_bytes() == original
    fresh = candidate("new")
    fresh.candidate_id = alias
    assert select_pairing_candidate([device], None, [fresh], alias) == fresh


def test_reserved_alias_in_existing_registry_is_preserved_and_rejected(registry):
    run(registry.register(candidate()))
    data = json.loads(registry.path.read_text())
    data["devices"][0]["aliases"] = ["candidate-one"]
    raw = json.dumps(data)
    registry.path.write_text(raw)
    with pytest.raises(AgentError) as error:
        run(registry.snapshot())
    assert error.value.details["reason"] == "invalid_registry"
    assert registry.path.read_text() == raw
