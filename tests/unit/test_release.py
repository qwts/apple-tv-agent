"""Release identity, complete asset sets, frozen workers and secure Linux selection."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/release"))
import publish  # noqa: E402
import version  # noqa: E402


def test_current_version_matches_and_tag_mismatch_fails():
    current = version.release_version()
    assert version.release_version("v" + current) == current
    with pytest.raises(ValueError):
        version.release_version("v9.9.9")


def test_stable_gate_requires_exact_version_and_all_targets(monkeypatch, tmp_path):
    monkeypatch.setattr(version, "ROOT", tmp_path)
    monkeypatch.setattr(version, "release_version", lambda tag: "1.0.0")
    gate = tmp_path / "release-gates.json"
    data = {"validated_version": "0.9.0", "platforms": dict.fromkeys(version.TARGETS, "passed")}
    gate.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        version.publication_version("v1.0.0")
    data["validated_version"] = "1.0.0"
    data["platforms"]["linux-x86_64"] = "not-tested"
    gate.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        version.publication_version("v1.0.0")
    data["platforms"]["linux-x86_64"] = "passed"
    gate.write_text(json.dumps(data))
    assert version.publication_version("v1.0.0") == "1.0.0"


def test_prerelease_does_not_require_native_gate(monkeypatch):
    monkeypatch.setattr(version, "release_version", lambda tag: "1.0.0rc1")
    assert version.publication_version("v1.0.0rc1") == "1.0.0rc1"


def test_assets_require_complete_set_and_valid_hashes(tmp_path):
    names = [
        f"apple-tv-agent-v1.0.0a1-{target}." + ("zip" if target.startswith("windows") else "tar.gz")
        for target in version.TARGETS
    ]
    names += ["apple_tv_agent-1.0.0a1-py3-none-any.whl", "apple_tv_agent-1.0.0a1.tar.gz"]
    for name in names:
        (tmp_path / name).write_bytes(b"synthetic")
        (tmp_path / (name + ".sha256")).write_text(
            hashlib.sha256(b"synthetic").hexdigest() + "  " + name
        )
    assert publish.verify_assets(tmp_path, "1.0.0a1")[0] == set(names)
    (tmp_path / names[0]).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        publish.verify_assets(tmp_path, "1.0.0a1")
    (tmp_path / names[0]).unlink()
    with pytest.raises(ValueError):
        publish.verify_assets(tmp_path, "1.0.0a1")


def test_frozen_decoder_uses_internal_worker(monkeypatch):
    from apple_tv_agent.observation import images

    process = Mock(returncode=0)
    process.communicate = AsyncMock(
        return_value=(b'{"width":8,"height":8,"quality":"usable"}', b"")
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(images, "require_decoder", lambda: None)
    monkeypatch.setattr(images.sys, "frozen", True, raising=False)
    monkeypatch.setattr(images.asyncio, "create_subprocess_exec", spawn)

    async def run():
        return await images.decode_image(
            b"synthetic", deadline=asyncio.get_running_loop().time() + 1
        )

    assert asyncio.run(run())["width"] == 8
    assert spawn.call_args.args == (sys.executable, "--internal-image-worker")


def test_linux_exact_secret_service_only(monkeypatch):
    import keyring

    from apple_tv_agent import credentials
    from apple_tv_agent.errors import AgentError

    class SecureBackend:
        pass

    monkeypatch.setitem(
        sys.modules, "keyring.backends.SecretService", SimpleNamespace(Keyring=SecureBackend)
    )
    monkeypatch.setattr(credentials.sys, "platform", "linux")
    monkeypatch.setattr(keyring, "get_keyring", lambda: SecureBackend())
    assert type(credentials.NativeCredentialStore().backend) is SecureBackend
    monkeypatch.setattr(keyring, "get_keyring", lambda: SimpleNamespace())
    with pytest.raises(AgentError) as error:
        credentials.NativeCredentialStore()
    assert error.value.details["reason"] == "native_backend_required"
    assert "D-Bus" in error.value.details["recovery"]


def test_linux_missing_session_is_fixed_error(monkeypatch):
    import keyring

    from apple_tv_agent import credentials
    from apple_tv_agent.errors import AgentError

    monkeypatch.setattr(credentials.sys, "platform", "linux")
    monkeypatch.setattr(
        keyring, "get_keyring", Mock(side_effect=RuntimeError("private session data"))
    )
    with pytest.raises(AgentError) as error:
        credentials.NativeCredentialStore()
    assert "private session data" not in str(error.value)
    assert error.value.details["reason"] == "vault_unavailable"


def test_workflow_publication_requires_all_validation():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]
    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["draft-release"]["permissions"] == {"contents": "write"}
    assert set(jobs["draft-release"]["needs"]) == {"identity", "smoke", "python-package"}
    assert "github.event_name == 'push'" in jobs["draft-release"]["if"]
    assert "refs/tags/v" in jobs["draft-release"]["if"]
    for name in ("bundle", "smoke"):
        assert {row["target"] for row in jobs[name]["strategy"]["matrix"]["include"]} == set(
            version.TARGETS
        )
    for job in jobs.values():
        assert job["timeout-minutes"] <= 20
        assert "self-hosted" not in job["runs-on"]
