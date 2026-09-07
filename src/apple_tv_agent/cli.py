"""Parse fully before constructing services; stdout is a single JSON response."""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Callable, Sequence
from ipaddress import IPv4Address
from typing import BinaryIO

from pydantic import TypeAdapter, ValidationError

from apple_tv_agent import __version__
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Command, Identifier, failure, success
from apple_tv_agent.ports import Service
from apple_tv_agent.request import Request
from apple_tv_agent.service import ContractService


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, message):
        # argparse's message may quote user data; emit a fixed public error instead.
        raise AgentError(ErrorCode.INVALID_ARGUMENT)


IDENTIFIER_ADAPTER = TypeAdapter(Identifier)


def identifier(value: str) -> str:
    try:
        return IDENTIFIER_ADAPTER.validate_python(value)
    except ValidationError:
        raise argparse.ArgumentTypeError("Invalid identifier.") from None


def number(value: str, lower: float, upper: float) -> float:
    try:
        result = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a finite number in range.") from None
    if not math.isfinite(result) or not lower <= result <= upper:
        raise argparse.ArgumentTypeError("Expected a finite number in range.")
    return result


def ipv4(value: str) -> str:
    try:
        return str(IPv4Address(value))
    except ValueError:
        raise argparse.ArgumentTypeError("Targeted discovery requires literal IPv4.") from None


def parser() -> Parser:
    root = Parser(
        prog="apple-tv-agent", description="Local Apple TV discovery and device management."
    )
    root.add_argument("--version", action="version", version=f"apple-tv-agent {__version__}")

    def common(target, device=False):
        target.add_argument(
            "--timeout",
            type=lambda v: number(v, 1, 120),
            default=argparse.SUPPRESS,
            metavar="SECONDS",
        )
        if device:
            target.add_argument("--device", type=identifier, default=argparse.SUPPRESS)

    common(root)
    top = root.add_subparsers(dest="group", required=True)
    for name in ("doctor", "discover", "pair", "status", "capabilities"):
        sub = top.add_parser(name)
        sub.set_defaults(command=name)
        common(sub, device=name in ("pair", "status", "capabilities"))
        if name == "doctor":
            sub.add_argument("--network", action="store_true")
        if name == "discover":
            sub.add_argument("--host", type=ipv4)

    groups = {
        "devices": ("list", "alias", "default", "forget"),
        "remote": (
            "up",
            "down",
            "left",
            "right",
            "select",
            "menu",
            "home",
            "play",
            "pause",
            "stop",
            "next",
            "previous",
        ),
        "power": ("on", "off"),
        "volume": ("up", "down", "set"),
        "apps": ("list", "launch"),
        "keyboard": ("type",),
    }
    for group, actions in groups.items():
        parent = top.add_parser(group)
        common(parent)
        children = parent.add_subparsers(dest="action", required=True)
        for action in actions:
            leaf = children.add_parser(action)
            leaf.set_defaults(command=f"{group}.{action}")
            common(leaf, device=(group, action) != ("devices", "list"))
            if (group, action) == ("devices", "alias"):
                leaf.add_argument("--name", required=True, type=identifier)
            if (group, action) == ("volume", "set"):
                leaf.add_argument("--level", required=True, type=lambda v: number(v, 0, 100))
            if (group, action) == ("apps", "launch"):
                leaf.add_argument("--app-id", required=True, type=identifier)
            if group == "keyboard":
                leaf.add_argument("--text-stdin", action="store_true", required=True)
    return root


def parse_request(argv: Sequence[str] | None, stdin: BinaryIO | None = None) -> Request:
    args = vars(parser().parse_args(argv))
    text = None
    if args.get("text_stdin"):
        stream = stdin if stdin is not None else sys.stdin.buffer
        if stream.isatty():
            raise AgentError(ErrorCode.INVALID_ARGUMENT, details={"reason": "pipe_text_to_stdin"})
        try:
            raw = stream.read(4097)
            if not isinstance(raw, bytes) or not 1 <= len(raw) <= 4096:
                raise ValueError()
            text = raw.decode("utf-8")
        except (ValueError, OSError):
            raise AgentError(
                ErrorCode.INVALID_ARGUMENT, details={"reason": "invalid_text_input"}
            ) from None
    return Request(
        command=Command(args["command"]),
        device=args.get("device"),
        timeout=args.get("timeout", 15),
        host=args.get("host"),
        name=args.get("name"),
        app_id=args.get("app_id"),
        level=args.get("level"),
        network=args.get("network", False),
        text=text,
    )


async def execute(service: Service, request: Request):
    if request.command == Command.PAIR:
        # Pairing owns separate human-input deadlines in issue 004.
        return await service.execute(request)
    deadline = asyncio.timeout(request.timeout)
    try:
        async with deadline:
            return await service.execute(request)
    except AgentError as error:
        if deadline.expired():
            # Services may translate cancellation to retain completed mutation details.
            raise AgentError(ErrorCode.TIMEOUT, details=error.details) from None
        raise


def main(
    argv=None,
    *,
    service_factory: Callable[[], Service] = ContractService,
    stdin: BinaryIO | None = None,
) -> int:
    command = None
    try:
        try:
            request = parse_request(argv, stdin)
        except SystemExit as error:
            # Only parser help/version may exit without a JSON envelope.
            return int(error.code or 0)
        command = request.command
        pairing_input = stdin if stdin is not None else sys.stdin
        if command == Command.PAIR and not pairing_input.isatty():
            raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
        if command == Command.PAIR and service_factory is ContractService:
            from apple_tv_agent.pin import read_pin

            service = ContractService(pin_reader=lambda: read_pin(stream=pairing_input))
        else:
            service = service_factory()
        result = asyncio.run(execute(service, request))
        response = success(command, result.device_id, result.data)
        exit_code = 0
    except (Exception, KeyboardInterrupt, SystemExit) as error:
        if isinstance(error, AgentError):
            public_error = error
        elif isinstance(error, TimeoutError):
            public_error = AgentError(ErrorCode.TIMEOUT)
        else:
            public_error = AgentError(ErrorCode.INTERNAL_ERROR)
        try:
            response = failure(command, public_error)
            exit_code = public_error.exit_code
        except Exception:
            # Invalid adapter-supplied error details must not cause a raw traceback.
            public_error = AgentError(ErrorCode.INTERNAL_ERROR)
            response = failure(command, public_error)
            exit_code = public_error.exit_code
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=True, allow_nan=False))
    return exit_code
