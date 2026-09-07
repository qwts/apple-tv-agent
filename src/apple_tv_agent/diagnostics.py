"""Local-first diagnostic observations with fixed, nonsecret recovery messages."""

import asyncio
import importlib
import importlib.metadata
import platform
import re
import sys

from apple_tv_agent import __version__
from apple_tv_agent.models import Check, DoctorData
from apple_tv_agent.pairing import private_protocol_logs
from apple_tv_agent.ports import CommandResult

DEPENDENCIES = {
    "aiohttp": ("aiohttp", "3.14.3"),
    "pyatv": ("pyatv", "0.18.0"),
    "keyring": ("keyring", "25.7.0"),
    "platformdirs": ("platformdirs", "4.11.7"),
    "pydantic": ("pydantic", "2.13.5"),
    "filelock": ("filelock", "3.32.5"),
}


def native_store():
    from apple_tv_agent.credentials import NativeCredentialStore

    return NativeCredentialStore()


def registry_store():
    from apple_tv_agent.registry import DeviceRegistry

    return DeviceRegistry()


def network_adapter():
    from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter

    return PyatvAdapter()


class DoctorService:
    def __init__(
        self,
        *,
        registry_factory=registry_store,
        vault_factory=native_store,
        adapter_factory=network_adapter,
        version=importlib.metadata.version,
        import_module=importlib.import_module,
    ):
        self.registry_factory = registry_factory
        self.vault_factory = vault_factory
        self.adapter_factory = adapter_factory
        self.version = version
        self.import_module = import_module

    async def execute(self, request):
        checks = []

        def add(name, status, message):
            checks.append(Check(name=name, status=status, message=message))

        with private_protocol_logs():
            add(
                "python",
                "pass" if sys.version_info >= (3, 12) else "fail",
                "Python 3.12 or newer is required; use the package's supported interpreter.",
            )
            add(
                "host",
                "pass" if sys.platform in ("darwin", "win32") else "fail",
                "Native macOS or Windows is required for credential storage; hardware validation is separate.",
            )
            add(
                "executable_context",
                "pass",
                "Running in a virtual environment."
                if sys.prefix != sys.base_prefix
                else "Running outside a virtual environment; use an isolated environment for dependency recovery.",
            )
            for distribution, (module, required) in DEPENDENCIES.items():
                try:
                    version = self.version(distribution)
                    if not isinstance(version, str) or not re.fullmatch(
                        r"[0-9A-Za-z.+_-]{1,80}", version
                    ):
                        raise ValueError()
                    if version != required:
                        add(
                            "dependency_" + distribution,
                            "fail",
                            f"Installed version: {version}; required version: {required}. "
                            "Reinstall with the locked setup instructions in docs/cli-contract.md.",
                        )
                        continue
                    self.import_module(module)
                except Exception:
                    add(
                        "dependency_" + distribution,
                        "fail",
                        "Dependency missing or unusable. Reinstall with the locked setup instructions in docs/cli-contract.md.",
                    )
                else:
                    add("dependency_" + distribution, "pass", "Installed version: " + version)
            try:
                self.vault_factory()
            except Exception:
                add(
                    "native_backend",
                    "fail",
                    "Native credential backend unavailable. Use macOS Keychain or Windows Credential Manager in your signed-in desktop session; see docs/troubleshooting.md.",
                )
            else:
                add(
                    "native_backend",
                    "pass",
                    "Expected native backend selected; no credential was read or written.",
                )
            add(
                "vault_access",
                "not_tested",
                "Backend selection cannot establish that the vault is unlocked. Run status to test saved credentials; unlock the vault or allow the local OS prompt if needed.",
            )
            try:
                snapshot = await self.registry_factory().snapshot()
            except asyncio.CancelledError:
                raise
            except Exception:
                add(
                    "registry",
                    "fail",
                    "Registry unreadable, invalid or busy. Preserve it before recovery; close competing commands and follow docs/registry.md. It was not repaired or reset.",
                )
            else:
                add("registry", "pass", "Registry readable and valid.")
                if not snapshot.devices:
                    add(
                        "pairing_records",
                        "not_tested",
                        "No registered devices. Run discover, then pair in a local terminal.",
                    )
                elif not any(device.paired_protocols for device in snapshot.devices):
                    add(
                        "pairing_records",
                        "not_tested",
                        "Registered devices have no saved pairing markers. Run pair in a local terminal.",
                    )
                else:
                    add(
                        "pairing_records",
                        "pass",
                        "Pairing markers exist; credential presence and device authentication were not tested.",
                    )
            if not request.network:
                add(
                    "network",
                    "not_tested",
                    "LAN discovery not requested. Run doctor --network to scan without pairing or control.",
                )
            else:
                loop = asyncio.get_running_loop()
                end = (
                    request.deadline
                    if request.deadline is not None
                    else loop.time() + request.timeout
                )
                budget = max(0, end - loop.time()) * 0.8
                try:
                    async with asyncio.timeout(budget):
                        devices = await self.adapter_factory().discover(host=None, timeout=budget)
                except TimeoutError:
                    add(
                        "network",
                        "fail",
                        "Discovery exceeded its time budget. Check connectivity and retry; no firewall cause was established.",
                    )
                except Exception:
                    add(
                        "network",
                        "fail",
                        "Discovery failed. Check local-network permission, active VPN and network isolation; see docs/troubleshooting.md. No firewall cause was established.",
                    )
                else:
                    if devices:
                        add(
                            "network",
                            "pass",
                            f"Observed {len(devices)} Apple TV discovery candidate(s). Authentication and control were not tested.",
                        )
                    else:
                        add(
                            "network",
                            "not_tested",
                            "No Apple TV replies observed. Check TV connectivity, VPN, guest isolation and local permissions; try discover --host IPV4. An empty scan does not establish a firewall failure.",
                        )
        return CommandResult(
            None,
            DoctorData(
                version=__version__,
                python=platform.python_version(),
                platform=sys.platform,
                checks=checks,
            ),
        )
