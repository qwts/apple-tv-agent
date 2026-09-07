"""Build one native bundle and an archive; inputs come only from tracked package resources."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from version import ROOT, TARGETS, release_version


def run(*args):
    subprocess.run(args, check=True, cwd=ROOT)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(target):
    host = {"darwin": "macos", "win32": "windows", "linux": "linux"}[sys.platform]
    arch = {"arm64": "arm64", "aarch64": "arm64", "amd64": "x86_64", "x86_64": "x86_64"}[
        platform.machine().lower()
    ]
    if target != f"{host}-{arch}":
        raise ValueError("Target must match the native build host")
    version = release_version()
    output = ROOT / "release-dist"
    output.mkdir(exist_ok=True)
    name = f"apple-tv-agent-v{version}-{target}"
    stage = ROOT / "build/release" / name
    if stage.exists():
        shutil.rmtree(stage)
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "build/frozen"),
        "--workpath",
        str(ROOT / "build/pyinstaller"),
        str(ROOT / "tools/release/bundle.spec"),
    )
    shutil.copytree(ROOT / "build/frozen/apple-tv-agent", stage, symlinks=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    shutil.copy2(stage / f"apple-tv-agent{suffix}", stage / f"apple-tv-screen{suffix}")
    shutil.copytree(ROOT / "skills", stage / "skills")
    shutil.copytree(ROOT / "schemas", stage / "schemas")
    shutil.copytree(ROOT / "docs", stage / "docs")
    (stage / "README.md").write_text(
        "# Apple TV Agent\n\n"
        "Start with [download, setup and upgrade instructions](docs/downloads.md). "
        "Keep both executables beside the _internal directory. Python is included. "
        "The portable agent skill is in skills/apple-tv-control.\n"
    )
    notices = stage / "licenses"
    notices.mkdir()
    # Include distribution metadata and shipped license texts, including build/runtime components.
    components = []
    for dist in importlib.metadata.distributions():
        name_ = dist.metadata["Name"]
        components.append({"name": name_, "version": dist.version})
        directory = notices / name_
        directory.mkdir(exist_ok=True)
        (directory / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
        for file in dist.files or []:
            if any(
                token in part.lower()
                for part in file.parts
                for token in ("license", "copying", "notice")
            ):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    destination = directory / str(file).replace("/", "_").replace("\\", "_")
                    shutil.copy2(source, destination)
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if not python_license.is_file():
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python license was not found; do not distribute without it")
    shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    shutil.copy2(ROOT / "src/apple_tv_agent/observation/bscpylgtv-LICENSE.txt", notices)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    provenance = {
        "version": version,
        "commit": commit,
        "target": target,
        "python": platform.python_version(),
        "build_os": platform.platform(),
        "uv_lock_sha256": digest(ROOT / "uv.lock"),
        "signing": "ad-hoc, not notarized" if host == "macos" else "unsigned",
        "components": sorted(components, key=lambda item: item["name"].lower()),
    }
    (stage / "BUILD.json").write_text(json.dumps(provenance, indent=2) + "\n")
    # Preserve POSIX executable bits and PyInstaller's safe relative dylib symlinks in tar.
    archive = Path(
        shutil.make_archive(
            str(output / name),
            "zip" if host == "windows" else "gztar",
            root_dir=stage.parent,
            base_dir=stage.name,
        )
    )
    (output / (archive.name + ".sha256")).write_text(f"{digest(archive)}  {archive.name}\n")
    print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=TARGETS, required=True)
    build(parser.parse_args().target)
