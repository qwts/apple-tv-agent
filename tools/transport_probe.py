#!/usr/bin/env python3
"""Opt-in feasibility probe, not the production CLI. Never persists TV secrets."""

import argparse
import asyncio
from contextlib import contextmanager
from importlib.metadata import metadata, version
from ipaddress import IPv4Address
import json
import logging
import os
import platform
import secrets
import sys
import uuid

import keyring
import pyatv
from pyatv.const import FeatureName, FeatureState, PairingRequirement, Protocol
from pyatv.storage.memory_storage import MemoryStorage


class ProbeError(Exception):
    """Only fixed, nonsecret codes cross the output boundary."""


class ActionState:
    """Track possible playback dispatch for one CLI invocation."""

    def __init__(self):
        self.attempted = False


def native_vault():
    backend = keyring.get_keyring()
    expected = {
        "Darwin": "keyring.backends.macOS.Keyring",
        "Windows": "keyring.backends.Windows.WinVaultKeyring",
    }.get(platform.system())
    actual = f"{type(backend).__module__}.{type(backend).__name__}"
    if actual != expected:
        raise ProbeError("NATIVE_VAULT_REQUIRED")
    return backend, actual


def environment():
    packages = {}
    for name in ("pyatv", "keyring"):
        info = metadata(name)
        packages[name] = {
            "version": version(name),
            "requires_python": info["Requires-Python"],
            "license": info["License-Expression"] or info["License"],
        }
    _, backend = native_vault()
    return {
        "os": platform.system(),
        "os_version": platform.mac_ver()[0] or platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "packages": packages,
        "vault_backend": backend,
        "vault_access": "not_tested",
    }


def vault_roundtrip():
    backend, name = native_vault()
    service = "apple-tv-agent.transport-probe"
    account = str(uuid.uuid4())
    value = secrets.token_urlsafe(32)
    try:
        backend.set_password(service, account, value)
        if backend.get_password(service, account) != value:
            raise ProbeError("VAULT_READBACK_FAILED")
    finally:
        # Attempt cleanup even if a write raised after possibly storing the value.
        try:
            backend.delete_password(service, account)
        except keyring.errors.PasswordDeleteError:
            if backend.get_password(service, account) is not None:
                raise ProbeError("VAULT_CLEANUP_FAILED") from None
    if backend.get_password(service, account) is not None:
        raise ProbeError("VAULT_CLEANUP_FAILED")
    return {"vault_backend": name, "roundtrip": "passed", "cleanup": "passed"}


@contextmanager
def terminal_reader():
    """Nonblocking hidden PIN input, so cancellation leaves no blocked thread."""
    if not sys.stdin.isatty():
        raise ProbeError("INTERACTIVE_REQUIRED")
    if os.name == "nt":
        import msvcrt

        def read():
            return msvcrt.getwch() if msvcrt.kbhit() else ""

        yield read
    else:
        import select
        import termios

        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
        hidden = termios.tcgetattr(fd)
        hidden[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(fd, termios.TCSAFLUSH, hidden)
        try:
            def read():
                if not select.select([fd], [], [], 0)[0]:
                    return ""
                value = os.read(fd, 1)
                if not value:
                    raise ProbeError("PIN_INPUT_CLOSED")
                return value.decode("ascii", errors="ignore")

            yield read
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, original)


async def read_pin(timeout=120):
    print("Enter the PIN displayed on the selected TV (hidden): ",
          end="", file=sys.stderr, flush=True)
    try:
        with terminal_reader() as read:
            async with asyncio.timeout(timeout):
                pin = ""
                extended = False
                while True:
                    char = read()
                    if extended and char:
                        extended = False
                    elif char in ("\x00", "\xe0"):
                        extended = True
                    elif char in ("\r", "\n"):
                        if len(pin) != 4:
                            raise ProbeError("INVALID_PIN")
                        return pin
                    elif char in ("\x03", "\x04", "\x1a"):
                        raise ProbeError("CANCELED")
                    elif char in ("\x08", "\x7f"):
                        pin = pin[:-1]
                    elif char and char in "0123456789":
                        pin += char
                        if len(pin) > 4:
                            raise ProbeError("INVALID_PIN")
                    await asyncio.sleep(0.02)
    finally:
        print(file=sys.stderr)


def summarize_device(device):
    # Never serialize config/service objects, properties, credentials or MACs.
    return {
        "identifier": device.identifier,
        "name": device.name,
        "address": str(device.address),
        "device_info": {
            "model": device.device_info.model.name,
            "operating_system": device.device_info.operating_system.name,
            "version": device.device_info.version,
        },
        "services": [
            {"protocol": service.protocol.name,
             "pairing": service.pairing.name,
             "enabled": service.enabled}
            for service in device.services
        ],
    }


async def pair_once(device, protocol, storage, timeout):
    service = device.get_service(protocol)
    if service is None or not service.enabled:
        raise ProbeError("PROTOCOL_UNAVAILABLE")
    if service.pairing in (PairingRequirement.Disabled, PairingRequirement.Unsupported):
        raise ProbeError("PAIRING_UNAVAILABLE")
    async with asyncio.timeout(timeout):
        handler = await pyatv.pair(
            device, protocol, asyncio.get_running_loop(), storage=storage
        )
    try:
        if not handler.device_provides_pin:
            raise ProbeError("DEVICE_PIN_REQUIRED")
        # One attempt per invocation; begin, prompt and finish share a deadline.
        async with asyncio.timeout(120):
            print(f"Pairing {protocol.name}…", file=sys.stderr, flush=True)
            try:
                await handler.begin()
            except Exception:
                raise ProbeError(f"PAIRING_{protocol.name.upper()}_BEGIN_FAILED") from None
            handler.pin(await read_pin())
            try:
                await handler.finish()
            except Exception:
                raise ProbeError(f"PAIRING_{protocol.name.upper()}_FINISH_FAILED") from None
            if not handler.has_paired:
                raise ProbeError("PAIRING_FAILED")
    finally:
        async with asyncio.timeout(timeout):
            await handler.close()


async def inspect_connection(device, storage, timeout, pause=False, play=False,
                             action_state=None):
    if action_state is None:
        action_state = ActionState()
    if pause and play:
        raise ProbeError("CONFLICTING_ACTIONS")
    connection = None
    try:
        async with asyncio.timeout(timeout):
            connection = await pyatv.connect(
                device, asyncio.get_running_loop(), storage=storage
            )
            capabilities = {
                name.name: info.state.name.lower()
                for name, info in connection.features.all_features(
                    include_unsupported=True
                ).items()
            }
            # Exclude titles and keyboard contents from probe evidence.
            playing = await connection.metadata.playing()
            result = {
                "capabilities": capabilities,
                "playback_state": playing.device_state.name.lower(),
                "pause_outcome": "not_requested",
                "play_outcome": "not_requested",
            }
            if connection.features.in_state(
                FeatureState.Available, FeatureName.TextFocusState
            ):
                result["keyboard_focus"] = connection.keyboard.text_focus_state.name.lower()
            if pause:
                if not connection.features.in_state(
                    FeatureState.Available, FeatureName.Pause
                ):
                    raise ProbeError("PAUSE_UNAVAILABLE")
                # No mutation retry; successful dispatch alone is not confirmation.
                operation = connection.remote_control.pause
                action_state.attempted = True
                await operation()
                result["pause_outcome"] = "sent"
            if play:
                if not connection.features.in_state(
                    FeatureState.Available, FeatureName.Play
                ):
                    raise ProbeError("PLAY_UNAVAILABLE")
                operation = connection.remote_control.play
                action_state.attempted = True
                await operation()
                result["play_outcome"] = "sent"
                observed = await connection.metadata.playing()
                result["playback_state_after"] = observed.device_state.name.lower()
                if result["playback_state_after"] == "playing":
                    result["play_outcome"] = "confirmed"
            return result
    finally:
        if connection is not None:
            tasks = connection.close()
            if tasks:
                async with asyncio.timeout(timeout):
                    await asyncio.gather(*tasks)


async def network_probe(args, action_state=None):
    if args.command == "session" and not sys.stdin.isatty():
        raise ProbeError("INTERACTIVE_REQUIRED")
    storage = MemoryStorage()
    await storage.load()
    async with asyncio.timeout(args.timeout + 2):
        devices = await pyatv.scan(
            asyncio.get_running_loop(), timeout=args.timeout,
            hosts=[args.host] if args.host else None, storage=storage,
        )
    if args.command == "discover":
        return {"devices": [summarize_device(device) for device in devices]}
    matches = [d for d in devices if args.identifier in d.all_identifiers]
    if len(matches) != 1:
        raise ProbeError("DEVICE_NOT_UNIQUE")
    device = matches[0]
    for name in args.protocol:
        await pair_once(device, Protocol[name], storage, args.timeout)
    return await inspect_connection(
        device, storage, args.timeout, args.pause, args.play, action_state
    )


def ipv4(value):
    try:
        return str(IPv4Address(value))
    except ValueError:
        raise argparse.ArgumentTypeError("Use a literal IPv4 address; pyatv 0.18 rejects IPv6.") from None


def bounded_timeout(value):
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Timeout must be an integer from 1 to 120.") from None
    if not 1 <= seconds <= 120:
        raise argparse.ArgumentTypeError("Timeout must be an integer from 1 to 120.")
    return seconds


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("environment", help="Versions and backend type; no LAN or vault access")
    commands.add_parser("vault-roundtrip", help="Write/read/delete one random test secret")
    for command in ("discover", "session"):
        sub = commands.add_parser(command)
        sub.add_argument("--host", type=ipv4)
        sub.add_argument("--timeout", type=bounded_timeout, default=5)
        if command == "session":
            sub.add_argument("--identifier", required=True)
            sub.add_argument("--protocol", action="append", required=True,
                             choices=["AirPlay", "Companion"])
            actions = sub.add_mutually_exclusive_group()
            actions.add_argument("--pause", action="store_true",
                             help="Explicitly send one pause after ephemeral pairing")
            actions.add_argument("--play", action="store_true",
                                 help="Explicitly send one play after ephemeral pairing")
    return root


def main(argv=None):
    logging.disable(logging.CRITICAL)  # Library debug records can contain protocol secrets.
    args = parser().parse_args(argv)
    action_state = ActionState()
    try:
        if args.command == "environment":
            data = environment()
        elif args.command == "vault-roundtrip":
            data = vault_roundtrip()
        else:
            data = asyncio.run(network_probe(args, action_state))
        print(json.dumps({"ok": True, "data": data}))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # Exception messages may contain credentials. Never print repr or traceback.
        code = str(error) if isinstance(error, ProbeError) else type(error).__name__
        outcome = None
        if getattr(args, "pause", False) or getattr(args, "play", False):
            outcome = "unknown" if action_state.attempted else "not_sent"
        print(json.dumps({"ok": False, "error": code,
                          "outcome": outcome}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
