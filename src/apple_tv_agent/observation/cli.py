"""Experimental LG discovery, trusted pairing and one-shot screen capture."""

import argparse
import asyncio
import json
import math
import sys
from dataclasses import asdict
from uuid import UUID

from apple_tv_agent.errors import ERRORS, AgentError, ErrorCode
from apple_tv_agent.observation.capture import CaptureService
from apple_tv_agent.observation.discovery import discover, inspect_certificate, local_host, uuid_udn
from apple_tv_agent.observation.images import require_decoder
from apple_tv_agent.observation.pairing import PairingService
from apple_tv_agent.observation.registry import LGRegistry


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise AgentError(ErrorCode.INVALID_ARGUMENT)


async def dispatch(args):
    deadline = asyncio.get_running_loop().time() + args.timeout
    if args.command == "discover":
        return {
            "candidates": [asdict(c) for c in await discover(deadline=deadline, host=args.host)]
        }
    if args.command in ("bind", "bindings", "unbind", "capture", "discard", "cleanup"):
        service = CaptureService()
        if args.command == "bind":
            return await service.bind(args.device, args.apple_tv, args.hdmi, args.timeout)
        if args.command == "capture":
            return await service.capture(args.binding, args.timeout)
        if args.command == "unbind":
            return await service.unbind(args.binding, args.timeout)
        try:
            async with asyncio.timeout_at(deadline):
                if args.command == "bindings":
                    return (await service.bindings.snapshot()).model_dump(mode="json")
                if args.command == "discard":
                    await service.artifacts.discard(args.observation)
                    return {"observation_id": args.observation, "deleted": True}
                return {"deleted_count": await service.artifacts.cleanup()}
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None
    if args.command == "devices":
        try:
            async with asyncio.timeout_at(deadline):
                data = await LGRegistry().snapshot()
        except TimeoutError:
            raise AgentError(ErrorCode.TIMEOUT) from None
        return {"devices": [d.model_dump(mode="json") for d in data.devices]}
    if args.command == "pair":
        return await PairingService().pair(args.host, args.udn, args.timeout)
    if args.command == "verify":
        return await PairingService().verify(args.device, args.host, args.timeout)
    if args.command == "forget":
        return await PairingService().forget(args.device, args.timeout)
    return {
        "host": args.host,
        "port": 3001,
        "certificate_sha256": await inspect_certificate(args.host, deadline=deadline),
        "trusted": False,
    }


def main(argv=None):
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "discover",
        "inspect",
        "pair",
        "devices",
        "verify",
        "forget",
        "bind",
        "bindings",
        "unbind",
        "capture",
        "discard",
        "cleanup",
    ):
        child = commands.add_parser(command)
        if command in ("discover", "inspect", "pair", "verify"):
            child.add_argument("--host", required=command in ("inspect", "pair"))
        if command == "pair":
            child.add_argument("--udn", required=True)
        if command in ("verify", "forget", "bind"):
            child.add_argument("--device", required=True)
        if command == "bind":
            child.add_argument("--apple-tv", required=True)
            child.add_argument("--hdmi", required=True, type=int, choices=[1, 2, 3, 4])
        if command in ("capture", "unbind"):
            child.add_argument("--binding", required=True)
        if command == "discard":
            child.add_argument("--observation", required=True)
        child.add_argument("--timeout", type=float, default=15)
    command = None
    try:
        args = parser.parse_args(argv)
        command = args.command
        if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 120:
            raise AgentError(ErrorCode.INVALID_ARGUMENT)
        if getattr(args, "host", None) is not None:
            args.host = local_host(args.host)
        try:
            if hasattr(args, "udn"):
                args.udn = uuid_udn(args.udn)
            for name in ("device", "apple_tv", "binding", "observation"):
                if hasattr(args, name):
                    setattr(args, name, str(UUID(getattr(args, name))))
        except ValueError:
            raise AgentError(ErrorCode.INVALID_ARGUMENT) from None
        if args.command == "pair" and not sys.stdin.isatty():
            raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
        if args.command == "capture":
            require_decoder()
        data = asyncio.run(dispatch(args))
        result = {"schema_version": 1, "command": command, "ok": True, "data": data, "error": None}
        code = 0
    except (Exception, KeyboardInterrupt, asyncio.CancelledError) as exc:
        error = exc if isinstance(exc, AgentError) else AgentError(ErrorCode.INTERNAL_ERROR)
        # No raw exception, peer payload, URL, or user-provided invalid argument.
        code, message = ERRORS[error.code]
        if error.code == ErrorCode.INVALID_ARGUMENT:
            message = "Invalid arguments. Run apple-tv-screen --help for usage."
        reason = error.details.get("reason")
        if reason == "screen_extra_required":
            message = (
                "Install the locked screen extra (uv sync --locked --extra screen) for capture."
            )
        elif reason == "input_mismatch":
            message = "LG foreground input does not match the selected HDMI binding."
        elif reason == "invalid_image":
            message = "The TV returned an invalid, oversized or truncated JPEG."
        result = {
            "schema_version": 1,
            "command": command,
            "ok": False,
            "data": None,
            "error": {"code": error.code.value, "message": message},
        }
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
