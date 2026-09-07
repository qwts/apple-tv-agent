"""Pinned SSAP registration and a fixed read allowlist. No arbitrary URI forwarding."""

import asyncio
import json
from contextlib import asynccontextmanager
from importlib.resources import files

import aiohttp

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation.discovery import local_host

READS = {
    "capture": "ssap://tv/executeOneShot",
    "system": "ssap://system/getSystemInfo",
    "foreground": "ssap://com.webos.applicationManager/getForegroundAppInfo",
}


def manifest():
    return json.loads(
        files("apple_tv_agent.observation").joinpath("lg-manifest.json").read_text(encoding="utf-8")
    )


async def reject_redirect(session, context, params):
    raise AgentError(ErrorCode.IDENTITY_MISMATCH)


@asynccontextmanager
async def pinned_socket(host, fingerprint, *, deadline):
    host = local_host(host)
    trace = aiohttp.TraceConfig()
    trace.on_request_redirect.append(reject_redirect)
    try:
        async with asyncio.timeout_at(deadline):
            async with aiohttp.ClientSession(
                trust_env=False, trace_configs=[trace], timeout=aiohttp.ClientTimeout(total=None)
            ) as http:
                async with http.ws_connect(
                    f"wss://{host}:3001",
                    ssl=aiohttp.Fingerprint(bytes.fromhex(fingerprint)),
                    max_msg_size=64 * 1024,
                    timeout=aiohttp.ClientWSTimeout(ws_close=1),
                ) as ws:
                    # Fingerprint validation has completed before the caller can load a key.
                    yield ws
    except aiohttp.ServerFingerprintMismatch:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH) from None
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    except (aiohttp.ClientError, OSError):
        raise AgentError(ErrorCode.NETWORK_ERROR) from None


async def message(ws, request_id):
    # Bound unrelated messages in addition to the socket and overall time/size limits.
    for _ in range(32):
        incoming = await ws.receive()
        if incoming.type != aiohttp.WSMsgType.TEXT:
            raise AgentError(ErrorCode.NETWORK_ERROR)
        try:
            data = json.loads(incoming.data)
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, TypeError):
            raise AgentError(ErrorCode.NETWORK_ERROR) from None
        if data.get("id") == request_id:
            return data
    raise AgentError(ErrorCode.NETWORK_ERROR)


async def register(ws, key=None):
    payload = {"pairingType": "PROMPT", "forcePairing": False, "manifest": manifest()}
    if key is not None:
        payload["client-key"] = key
    await ws.send_json({"id": "register", "type": "register", "payload": payload})
    for _ in range(4):
        data = await message(ws, "register")
        if data.get("type") == "registered":
            result = data.get("payload")
            value = result.get("client-key") if isinstance(result, dict) else None
            if not isinstance(value, str) or not 1 <= len(value) <= 4096 or not value.isprintable():
                raise AgentError(ErrorCode.AUTH_FAILED)
            return value
        if data.get("type") == "error":
            raise AgentError(ErrorCode.AUTH_FAILED)
        result = data.get("payload")
        if (
            data.get("type") != "response"
            or not isinstance(result, dict)
            or result.get("pairingType") != "PROMPT"
        ):
            raise AgentError(ErrorCode.AUTH_FAILED)
        # Saved-key rejection must never silently prompt for a replacement pairing.
        if key is not None:
            raise AgentError(ErrorCode.AUTH_FAILED)
    raise AgentError(ErrorCode.AUTH_FAILED)


async def read(ws, name):
    if name not in READS:
        raise AgentError(ErrorCode.INVALID_ARGUMENT)
    await ws.send_json({"id": name, "type": "request", "uri": READS[name], "payload": {}})
    data = await message(ws, name)
    payload = data.get("payload")
    if data.get("type") == "error":
        raise AgentError(ErrorCode.FEATURE_UNAVAILABLE)
    if (
        data.get("type") != "response"
        or not isinstance(payload, dict)
        or payload.get("returnValue") is not True
    ):
        raise AgentError(ErrorCode.NETWORK_ERROR)
    return payload
