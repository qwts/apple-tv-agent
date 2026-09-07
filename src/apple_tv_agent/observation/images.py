"""Same-TV pinned HTTPS fetch and killable image validation."""

import asyncio
import json
import sys
from urllib.parse import urlsplit

import aiohttp

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation.discovery import local_host
from apple_tv_agent.observation.models import MAX_IMAGE_BYTES


def require_decoder():
    try:
        import PIL

        if PIL.__version__ != "12.3.0":
            raise ImportError
    except ImportError:
        raise AgentError(
            ErrorCode.CONFIG_ERROR, details={"reason": "screen_extra_required"}
        ) from None


def image_url(value, host, port=None):
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
        or "\\" in value
    ):
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    try:
        uri = urlsplit(value)
        actual_port = 443 if uri.port is None else uri.port
        if (
            uri.scheme != "https"
            or uri.hostname != local_host(host)
            or uri.username is not None
            or uri.password is not None
            or uri.fragment
            or not 1 <= actual_port <= 65535
            or (port is not None and actual_port != port)
        ):
            raise ValueError
    except ValueError:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH) from None
    return actual_port


async def fetch_image(url, host, port, fingerprint, *, deadline):
    image_url(url, host, port)
    try:
        async with asyncio.timeout_at(deadline):
            async with aiohttp.ClientSession(
                trust_env=False, auto_decompress=False, timeout=aiohttp.ClientTimeout(total=None)
            ) as http:
                async with http.get(
                    url, ssl=aiohttp.Fingerprint(bytes.fromhex(fingerprint)), allow_redirects=False
                ) as response:
                    if 300 <= response.status < 400:
                        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
                    if response.status != 200:
                        raise AgentError(ErrorCode.NETWORK_ERROR)
                    if (
                        response.content_length is not None
                        and response.content_length > MAX_IMAGE_BYTES
                    ):
                        raise AgentError(
                            ErrorCode.CONFIG_ERROR, details={"reason": "invalid_image"}
                        )
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw) > MAX_IMAGE_BYTES:
                            raise AgentError(
                                ErrorCode.CONFIG_ERROR, details={"reason": "invalid_image"}
                            )
                    return bytes(raw)
    except aiohttp.ServerFingerprintMismatch:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH) from None
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    except (aiohttp.ClientError, OSError):
        raise AgentError(ErrorCode.NETWORK_ERROR) from None


async def decode_image(raw, *, deadline):
    require_decoder()
    process = None
    try:
        async with asyncio.timeout_at(deadline):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "apple_tv_agent.observation.image_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await process.communicate(raw)
            if process.returncode != 0:
                raise ValueError
            return json.loads(output)
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    except (ValueError, OSError):
        raise AgentError(ErrorCode.CONFIG_ERROR, details={"reason": "invalid_image"}) from None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
