"""Assemble verified assets into a draft release; never overwrite or publish a release."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from version import ROOT, TARGETS, publication_version


def verify_assets(directory, version):
    expected = {
        f"apple-tv-agent-v{version}-{target}."
        + ("zip" if target.startswith("windows") else "tar.gz")
        for target in TARGETS
    } | {f"apple_tv_agent-{version}-py3-none-any.whl", f"apple_tv_agent-{version}.tar.gz"}
    files = {p.name for p in directory.iterdir() if p.is_file()}
    if files != expected | {name + ".sha256" for name in expected}:
        raise ValueError("Release assets are missing, duplicated or unexpected")
    lines = []
    for name in sorted(expected):
        digest, recorded_name = (directory / (name + ".sha256")).read_text().split()
        with (directory / name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != actual or recorded_name != name:
            raise ValueError("Release asset checksum mismatch")
        lines.append(f"{actual}  {name}\n")
    return expected, "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    version = publication_version(args.tag)
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise ValueError("Invalid source commit")
    names, sums = verify_assets(args.assets, version)
    (args.assets / "SHA256SUMS").write_text(sums)
    provenance = {
        "version": version,
        "commit": args.commit,
        "repository": args.repository,
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "targets": list(TARGETS),
        "signing": "Unsigned preview; macOS ad-hoc only",
        "validation": "Archive smoke tests; see release-gates.json for native hardware gates",
    }
    (args.assets / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
    notes = ROOT / "build/release-notes.md"
    notes.parent.mkdir(exist_ok=True)
    notes.write_text(
        f"Version {version}, source commit `{args.commit}`.\n\n"
        "Download the archive matching your OS/architecture. Python and the optional LG decoder "
        "are included. Extract the entire folder; start with its README.md. Linux requires a "
        "desktop Secret Service keyring and D-Bus session.\n\n"
        "Preview bundles are unsigned (macOS ad-hoc, not notarized). Automated archive checks "
        "do not establish real-device compatibility. Review docs/downloads.md and the hardware "
        "validation ledger before use. SHA256SUMS checks bytes; PROVENANCE.json records build "
        "identity and is not a cryptographic attestation.\n"
    )
    # gh refuses an existing release; no upload --clobber, delete or public-edit operation exists here.
    command = [
        "gh",
        "release",
        "create",
        args.tag,
        "--repo",
        args.repository,
        "--verify-tag",
        "--target",
        args.commit,
        "--draft",
        "--title",
        f"Apple TV Agent {version}",
        "--notes-file",
        str(notes),
    ]
    if re.search(r"(?:a|b|rc)\d+$", version):
        command.append("--prerelease")
    command += [
        str(args.assets / name) for name in sorted(names | {"SHA256SUMS", "PROVENANCE.json"})
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
