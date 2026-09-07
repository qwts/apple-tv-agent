"""Explicit opt-in: write a random isolated credential, read in a new process, remove it."""

import os
import secrets
import subprocess
import sys
from uuid import uuid4

import pytest

from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.models import ProtocolName
from apple_tv_agent.observation.registry import LGCredentials


@pytest.mark.skipif(
    os.environ.get("APPLE_TV_AGENT_NATIVE_TEST") != "1", reason="native vault opt-in required"
)
@pytest.mark.parametrize(
    "store_type,protocol",
    [(NativeCredentialStore, ProtocolName.AIRPLAY), (LGCredentials, "ssap")],
    ids=["apple-tv", "lg"],
)
def test_native_vault_fresh_process_roundtrip(store_type, protocol):
    store = store_type()
    device_id = str(uuid4())
    secret = secrets.token_hex(32)
    try:
        store.set(device_id, protocol, secret)
        script = """
import sys
from apple_tv_agent.credentials import NativeCredentialStore
from apple_tv_agent.observation.registry import LGCredentials
store_type = {"NativeCredentialStore": NativeCredentialStore, "LGCredentials": LGCredentials}[sys.argv[2]]
value = store_type().get(sys.argv[1], sys.argv[3])
expected = sys.stdin.read()
raise SystemExit(0 if value == expected else 1)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, device_id, store_type.__name__, str(protocol)],
            input=secret,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == result.stderr == ""
    finally:
        store.delete(device_id, protocol)
    assert store.get(device_id, protocol) is None
