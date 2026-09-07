"""Private UUID-addressed artifacts with explicit and next-invocation expiry cleanup."""

import csv
import ctypes
import io
import os
import re
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from platformdirs import user_data_path
from pydantic import AwareDatetime, Field, model_validator

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import Model
from apple_tv_agent.observation.registry import LGRegistry


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or path.is_symlink()
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise AgentError(ErrorCode.CONFIG_ERROR)
    if os.name != "nt":
        if info.st_uid != os.getuid():
            raise AgentError(ErrorCode.CONFIG_ERROR)
        path.chmod(0o700)
        return
    # Replace, rather than append to, the directory DACL. Only the current SID inherits access.
    whoami = Path(os.environ["SystemRoot"]) / "System32/whoami.exe"
    result = subprocess.run(
        [str(whoami), "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    sid = next(csv.reader(io.StringIO(result.stdout)))[1]
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise AgentError(ErrorCode.CONFIG_ERROR)
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG),
    ]
    convert.restype = wintypes.BOOL
    apply = advapi.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    apply.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not convert(f"D:P(A;OICI;FA;;;{sid})", 1, ctypes.byref(descriptor), None):
        raise AgentError(ErrorCode.CONFIG_ERROR)
    try:
        if not apply(str(path), 0x80000004, descriptor):
            raise AgentError(ErrorCode.CONFIG_ERROR)
    finally:
        kernel.LocalFree(descriptor)


class OwnedArtifact(Model):
    observation_id: UUID
    delete_after: AwareDatetime


class Inventory(Model):
    schema_version: Literal[1] = 1
    artifacts: list[OwnedArtifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if len({a.observation_id for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("Duplicate artifacts")
        return self


class InventoryRegistry(LGRegistry):
    data_model = Inventory


class ArtifactStore:
    def __init__(self, root=None):
        self.root = (
            Path(root)
            if root is not None
            else user_data_path("apple-tv-agent", appauthor=False) / "captures"
        )
        self.registry = InventoryRegistry(self.root / "inventory.json")

    def path(self, observation_id):
        return self.root / f"{UUID(str(observation_id))}.jpg"

    def remove_file(self, observation_id):
        path = self.path(observation_id)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if (
            not stat.S_ISREG(info.st_mode)
            or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise AgentError(ErrorCode.CONFIG_ERROR)
        path.unlink()

    async def prepare(self):
        try:
            private_directory(self.root)
            # Protect the inventory and lock from link-based redirection before opening them.
            for path in (self.registry.path, Path(str(self.registry.path) + ".lock")):
                if path.is_symlink() or (
                    path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400
                ):
                    raise AgentError(ErrorCode.CONFIG_ERROR)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise AgentError(ErrorCode.CONFIG_ERROR) from None

    async def cleanup(self, *, now=None):
        await self.prepare()
        now = datetime.now(UTC) if now is None else now
        async with self.registry.transaction() as data:
            expired = [a for a in data.artifacts if a.delete_after <= now]
            for artifact in expired:
                self.remove_file(artifact.observation_id)
                data.artifacts.remove(artifact)
            self.registry._write(data)
            return len(expired)

    async def save(self, observation_id, raw, *, delete_after):
        await self.prepare()
        async with self.registry.transaction() as data:
            if any(a.observation_id == observation_id for a in data.artifacts):
                raise AgentError(ErrorCode.CONFIG_ERROR)
            path = self.path(observation_id)
            if path.exists() or path.is_symlink():
                raise AgentError(ErrorCode.CONFIG_ERROR)
            # Inventory first: a crash/partial write remains recoverable by UUID and expiry.
            data.artifacts.append(
                OwnedArtifact(observation_id=observation_id, delete_after=delete_after)
            )
            self.registry._write(data)
            created = False
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                if created:
                    self.remove_file(observation_id)
                data.artifacts = [a for a in data.artifacts if a.observation_id != observation_id]
                self.registry._write(data)
                raise
            return str(path.absolute())

    async def discard(self, observation_id):
        await self.prepare()
        observation_id = UUID(str(observation_id))
        async with self.registry.transaction() as data:
            owned = next((a for a in data.artifacts if a.observation_id == observation_id), None)
            if owned is None:
                return
            self.remove_file(observation_id)
            data.artifacts.remove(owned)
            self.registry._write(data)
