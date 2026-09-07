"""Explicit opt-in: write a random isolated credential, read in a new process, remove it."""

import os
import secrets
import subprocess
import sys
from uuid import uuid4

import pytest

from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.models import ProtocolName


@pytest.mark.skipif(
    os.environ.get("APPLE_TV_AGENT_NATIVE_TEST") != "1", reason="native vault opt-in required"
)
def test_native_vault_fresh_process_roundtrip():
    store = NativeCredentialStore()
    device_id = str(uuid4())
    secret = secrets.token_hex(32)
    try:
        store.set(device_id, ProtocolName.AIRPLAY, secret)
        script = """
import sys
from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.models import ProtocolName
value = NativeCredentialStore().get(sys.argv[1], ProtocolName.AIRPLAY)
expected = sys.stdin.read()
raise SystemExit(0 if value == expected else 1)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, device_id],
            input=secret,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == result.stderr == ""
    finally:
        store.delete(device_id, ProtocolName.AIRPLAY)
    assert store.get(device_id, ProtocolName.AIRPLAY) is None
