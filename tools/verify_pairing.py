"""Opt-in fresh-process credential reconnect check. Reads authentication only; no controls."""

import argparse
import asyncio
import json

from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter
from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.discovery import select_device
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.locking import device_lock
from apple_tv_agent.registry import DeviceRegistry


async def verify(device_id, timeout):
    registry = DeviceRegistry()
    data = await registry.snapshot()
    device = select_device(data.devices, data.default_device_id, device_id)
    async with device_lock(registry.path.parent / "locks", device.device_id):
        await PyatvAdapter().verify_saved(device, NativeCredentialStore(), timeout)
    return {"ok": True, "verified_protocols": [p.value for p in device.paired_protocols]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 120:
            raise AgentError(ErrorCode.INVALID_ARGUMENT)
        result = asyncio.run(verify(args.device, args.timeout))
    except (Exception, KeyboardInterrupt):
        # This diagnostic deliberately prints no exception, identity or secret values.
        print(json.dumps({"ok": False, "reason": "verification_failed"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
