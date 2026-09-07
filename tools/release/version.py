"""Release identity validation, shared by builds and publication."""

import json
import re
import tomllib
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("macos-arm64", "macos-x86_64", "windows-x86_64", "linux-x86_64")


def release_version(tag=None):
    value = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", value):
        raise ValueError("Version must be major.minor.patch with optional a/b/rc number")
    from apple_tv_agent import __version__

    if value != __version__ or (tag is not None and tag != "v" + value):
        raise ValueError("Tag, package and runtime versions must match")
    return value


def publication_version(tag):
    value = release_version(tag)
    if not Version(value).is_prerelease:
        gates = json.loads((ROOT / "release-gates.json").read_text())
        if gates.get("validated_version") != value or any(
            gates.get("platforms", {}).get(target) != "passed" for target in TARGETS
        ):
            raise ValueError(
                "Stable release blocked: record native platform validation for this version"
            )
    return value


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    print(publication_version(args.tag) if args.tag else release_version())
