"""Check a downloaded native archive in an unrelated directory with no Python on PATH."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_skill import validate as validate_skill


def check(archive):
    expected, name = archive.with_name(archive.name + ".sha256").read_text().split()
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected != actual or name != archive.name:
        raise ValueError("Archive checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="apple tv release ") as temporary:
        base = Path(temporary)
        extracted = base / "extracted bundle"
        extracted.mkdir()
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as source:
                if any(Path(n).is_absolute() or ".." in Path(n).parts for n in source.namelist()):
                    raise ValueError("Unsafe archive member")
                source.extractall(extracted)
        else:
            with tarfile.open(archive) as source:
                source.extractall(extracted, filter="data")
        roots = list(extracted.iterdir())
        if len(roots) != 1:
            raise ValueError("Expected one bundle root")
        bundle = roots[0]
        for path in bundle.rglob("*"):
            if any(
                p in (".local", ".git", ".venv", "captures", "lg-registry.json", "inventory.json")
                for p in path.relative_to(bundle).parts
            ):
                raise ValueError("Private development artifact in bundle")
        validate_skill(bundle / "skills/apple-tv-control")
        for schema in ("response-v1.json", "observation-v1.json"):
            if (
                json.loads((bundle / "schemas" / schema).read_text())["$schema"]
                != "https://json-schema.org/draft/2020-12/schema"
            ):
                raise ValueError("Missing schema")
        if not (bundle / "licenses/Python-LICENSE.txt").is_file():
            raise ValueError("Missing Python license")
        environment = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(key, None)
        environment["PATH"] = ""
        unrelated = base / "unrelated working directory"
        unrelated.mkdir()
        suffix = ".exe" if os.name == "nt" else ""

        def invoke(tool, args, expected=0, raw=None):
            result = subprocess.run(
                [str(bundle / (tool + suffix)), *args],
                cwd=unrelated,
                env=environment,
                input=raw,
                capture_output=True,
                timeout=30,
            )
            if result.returncode != expected or result.stderr:
                raise RuntimeError(
                    f"{tool} {args}: exit={result.returncode}, stderr={result.stderr!r}, stdout={result.stdout!r}"
                )
            return result.stdout

        version = json.loads((bundle / "BUILD.json").read_text())["version"]
        if version not in invoke("apple-tv-agent", ["--version"]).decode():
            raise ValueError("Runtime version mismatch")
        for tool in ("apple-tv-agent", "apple-tv-screen"):
            invoke(tool, ["--help"])
        for tool, args in (
            ("apple-tv-agent", ["remote", "unknown-action"]),
            ("apple-tv-screen", ["inspect"]),
        ):
            response = json.loads(invoke(tool, args, expected=2))
            if response["ok"] or response["error"]["code"] != "INVALID_ARGUMENT":
                raise ValueError("Invalid JSON contract")
        # Doctor is read-only; platform keyring absence is valid on headless runners.
        doctor = json.loads(invoke("apple-tv-agent", ["doctor"]))
        checks = doctor["data"]["checks"]
        if any(c["status"] != "pass" for c in checks if c["name"].startswith("dependency_")):
            raise ValueError("Bundled dependency import/metadata check failed")
        raw = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(raw, format="JPEG")
        result = json.loads(
            invoke("apple-tv-screen", ["--internal-image-check"], raw=raw.getvalue())
        )
        if result != {"width": 8, "height": 8, "quality": "usable"}:
            raise ValueError("Bundled worker subprocess failed")
    print(
        "Downloaded bundle: entry points, resources, dependency imports and worker passed without Python on PATH"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    check(parser.parse_args().archive.resolve())
