"""Frozen executable router; internal worker mode never enters the public CLI."""

import asyncio
import json
import sys
from pathlib import Path


def main():
    if sys.argv[1:] == ["--internal-runtime-check"]:
        import importlib
        from importlib.resources import files

        package = files("apple_tv_agent")
        for name in ("response-v1.json", "observation-v1.json", "observation/lg-manifest.json"):
            json.loads(package.joinpath(name).read_text(encoding="utf-8"))
        for name in ("docs/pairing.md", "docs/lg-capture.md", "skills/apple-tv-control/SKILL.md"):
            if not package.joinpath(name).read_text(encoding="utf-8"):
                raise RuntimeError("Empty bundled resource")
        backend = {"darwin": "macOS", "win32": "Windows", "linux": "SecretService"}[sys.platform]
        importlib.import_module("keyring.backends." + backend)
        print(json.dumps({"resources": "passed", "backend_import": "passed"}))
        return 0
    if sys.argv[1:] == ["--internal-image-worker"]:
        from apple_tv_agent.observation.image_worker import main as worker

        return worker()
    if sys.argv[1:] == ["--internal-image-check"]:
        from apple_tv_agent.observation.images import decode_image

        async def check():
            raw = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
            return await decode_image(raw, deadline=asyncio.get_running_loop().time() + 10)

        print(json.dumps(asyncio.run(check())))
        return 0
    if Path(sys.executable).stem == "apple-tv-screen":
        from apple_tv_agent.observation.cli import main as cli
    else:
        from apple_tv_agent.cli import main as cli
    return cli()


if __name__ == "__main__":
    raise SystemExit(main())
