import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_skill", ROOT / "tools/check_skill.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_skill_is_self_contained_after_copy(tmp_path):
    target = tmp_path / "client skills with spaces" / "apple-tv-control"
    shutil.copytree(ROOT / "skills/apple-tv-control", target)
    assert validator.validate(target)["name"] == "apple-tv-control"
    (target / "references/commands.md").unlink()
    with pytest.raises(ValueError, match="reference"):
        validator.validate(target)


def test_skill_cannot_link_outside_its_distribution(tmp_path):
    target = tmp_path / "apple-tv-control"
    shutil.copytree(ROOT / "skills/apple-tv-control", target)
    (tmp_path / "outside.md").write_text("outside")
    with (target / "SKILL.md").open("a") as file:
        file.write("\n[nonportable](../outside.md)\n")
    with pytest.raises(ValueError, match="reference"):
        validator.validate(target)


@pytest.mark.parametrize(
    "scenario,argv,code",
    [
        ("pause", ["remote", "pause", "--device", "living"], 0),
        ("ambiguous", ["devices", "list"], 0),
        ("vault", ["status"], 3),
        ("pairing", ["pair"], 3),
        ("volume", ["capabilities"], 0),
        ("next", ["remote", "next"], 5),
        ("hostile", ["apps", "list"], 0),
        ("unicode", ["keyboard", "type", "--text-stdin"], 0),
    ],
)
def test_walkthrough_cli_runs_outside_checkout(scenario, argv, code, tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/skill/fake_cli.py"), scenario, *argv],
        input="  café 🌍\n".encode(),
        capture_output=True,
        cwd=tmp_path,
    )
    assert result.returncode == code
    assert result.stderr == b""
    data = json.loads(result.stdout)
    assert data["schema_version"] == 1
    if scenario == "unicode":
        assert data["data"] == {"outcome": "sent", "observed_state": None}
    if scenario == "pairing":
        assert data["error"]["code"] == "INTERACTIVE_REQUIRED"
    if scenario == "next":
        assert data["error"]["details"]["outcome"] == "unknown"
        assert not data["error"]["retryable"]
