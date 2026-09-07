"""Frozen executable router; internal worker mode never enters the public CLI."""

import asyncio
import json
import sys
from pathlib import Path


def main():
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
