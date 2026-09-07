"""Validate portable skill metadata and resolve every local Markdown link within its folder."""

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


def validate(root):
    root = Path(root).resolve()
    content = (root / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", content, re.S)
    if not match:
        raise ValueError("Missing skill frontmatter")
    meta = yaml.safe_load(match[1])
    if not isinstance(meta, dict) or set(meta) != {"name", "description"}:
        raise ValueError("Expected name and description metadata")
    if meta["name"] != root.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta["name"]):
        raise ValueError("Skill name must match its directory")
    if not isinstance(meta["description"], str) or not 1 <= len(meta["description"]) <= 1024:
        raise ValueError("Invalid skill description")
    for file in root.rglob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
            parsed = urlsplit(target)
            if parsed.scheme in ("http", "https"):
                continue
            if parsed.scheme or not parsed.path:
                raise ValueError("Unsupported skill link")
            resolved = (file.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise ValueError("Missing or nonportable skill reference")
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path)
    validate(parser.parse_args().skill)
    print("Skill metadata and portable references passed.")
