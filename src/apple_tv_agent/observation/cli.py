"""Experimental LG discovery, trusted pairing and local credential management."""

import argparse
import asyncio
import json
import math
import sys
from dataclasses import asdict
from uuid import UUID

from apple_tv_agent.errors import ERRORS, AgentError, ErrorCode
from apple_tv_agent.observation.discovery import discover, inspect_certificate, local_host, uuid_udn
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
    for command in ("discover", "inspect", "pair", "devices", "verify", "forget"):
        child = commands.add_parser(command)
        if command in ("discover", "inspect", "pair", "verify"):
            child.add_argument("--host", required=command in ("inspect", "pair"))
        if command == "pair":
            child.add_argument("--udn", required=True)
        if command in ("verify", "forget"):
            child.add_argument("--device", required=True)
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
            if hasattr(args, "device"):
                args.device = str(UUID(args.device))
        except ValueError:
            raise AgentError(ErrorCode.INVALID_ARGUMENT) from None
        if args.command == "pair" and not sys.stdin.isatty():
            raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
        data = asyncio.run(dispatch(args))
        result = {"schema_version": 1, "command": command, "ok": True, "data": data, "error": None}
        code = 0
    except (Exception, KeyboardInterrupt, asyncio.CancelledError) as exc:
        error = exc if isinstance(exc, AgentError) else AgentError(ErrorCode.INTERNAL_ERROR)
        # No raw exception, peer payload, URL, or user-provided invalid argument.
        code, message = ERRORS[error.code]
        if error.code == ErrorCode.INVALID_ARGUMENT:
            message = "Invalid arguments. Run apple-tv-screen --help for usage."
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
