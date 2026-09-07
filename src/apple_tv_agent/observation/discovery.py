"""Untrusted LG candidate discovery; never loads credentials or establishes trust."""

import asyncio
import hashlib
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from ipaddress import IPv4Address
from urllib.parse import urlsplit
from uuid import UUID

import aiohttp

from apple_tv_agent.errors import AgentError, ErrorCode

SERVICE = "urn:schemas-upnp-org:device:MediaRenderer:1"
MAX_PACKET = 8192
MAX_DESCRIPTION = 64 * 1024
MAX_REPLIES = 128
MAX_CANDIDATES = 32
NS = "{urn:schemas-upnp-org:device-1-0}"


def invalid():
    return AgentError(ErrorCode.INVALID_ARGUMENT)


def local_host(value: str) -> str:
    try:
        address = IPv4Address(value)
        # Permit private/link-local LAN addresses, never loopback or other classes.
        if not (address.is_private or address.is_link_local) or any(
            (address.is_loopback, address.is_multicast, address.is_unspecified, address.is_reserved)
        ):
            raise ValueError
        return str(address)
    except (ValueError, TypeError):
        raise invalid() from None


@dataclass(frozen=True)
class Advertisement:
    host: str
    udn: str
    location: str


@dataclass(frozen=True)
class Candidate:
    host: str
    udn: str
    name: str
    model: str


def uuid_udn(value: str) -> str:
    if not value.startswith("uuid:"):
        raise ValueError("Invalid UDN")
    return f"uuid:{UUID(value[5:])}"


def description_url(value: str, host: str) -> str:
    if len(value) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise ValueError("Invalid URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "\\" in value
        or not 1 <= (parsed.port if parsed.port is not None else 80) <= 65535
    ):
        raise ValueError("Invalid URL")
    return value


def parse_reply(raw: bytes, sender: str) -> Advertisement | None:
    """Discard malformed/unrelated packets without echoing their content."""
    try:
        host = local_host(sender)
        if len(raw) > MAX_PACKET or b"\x00" in raw:
            return None
        lines = raw.decode("ascii").split("\r\n")
        if lines[0] != "HTTP/1.1 200 OK":
            return None
        headers = {}
        ended = False
        for line in lines[1:]:
            if not line:
                ended = True
                break
            name, value = line.split(":", 1)
            name = name.lower()
            if name != name.strip() or name in headers:
                return None
            headers[name] = value.strip()
        if not ended or headers.get("st") != SERVICE:
            return None
        identity, suffix = headers["usn"].split("::", 1)
        if suffix != SERVICE:
            return None
        return Advertisement(host, uuid_udn(identity), description_url(headers["location"], host))
    except (AgentError, ValueError, KeyError, UnicodeError):
        return None


def parse_description(raw: bytes, advertisement: Advertisement) -> Candidate | None:
    if len(raw) > MAX_DESCRIPTION or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        return None
    try:
        # Restrict to UTF-8 so alternate encodings cannot bypass the DTD guard.
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            return None
        root = ET.fromstring(text)
        device = root.find(f"{NS}device")
        if root.tag != f"{NS}root" or device is None:
            return None

        def field(name):
            nodes = device.findall(f"{NS}{name}")
            if len(nodes) != 1 or list(nodes[0]):
                raise ValueError
            value = (nodes[0].text or "").strip()
            if not value or len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError
            return value

        if field("deviceType") != SERVICE:
            return None
        manufacturer = field("manufacturer").casefold()
        if manufacturer not in ("lg", "lg electronics", "lg electronics.", "lg electronics inc."):
            return None
        if uuid_udn(field("UDN")) != advertisement.udn:
            return None
        return Candidate(
            advertisement.host, advertisement.udn, field("friendlyName"), field("modelName")
        )
    except (ET.ParseError, ValueError, UnicodeError):
        return None


async def advertisements(*, deadline: float, host: str | None = None) -> list[Advertisement]:
    loop = asyncio.get_running_loop()
    target = (local_host(host), 1900) if host is not None else ("239.255.255.250", 1900)
    request = (
        "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
        f'MAN: "ssdp:discover"\r\nMX: 1\r\nST: {SERVICE}\r\n\r\n'
    ).encode("ascii")
    results = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("0.0.0.0", 0))
        await loop.sock_sendto(sock, request, target)
        # Reserve the remaining request budget for description fetching and cleanup.
        scan_end = min(deadline, loop.time() + 2)
        for _ in range(MAX_REPLIES):
            try:
                async with asyncio.timeout_at(scan_end):
                    raw, sender = await loop.sock_recvfrom(sock, MAX_PACKET + 1)
            except TimeoutError:
                break
            if host is not None and sender[0] != target[0]:
                continue
            reply = parse_reply(raw, sender[0])
            if reply is not None:
                results[(reply.host, reply.udn, reply.location)] = reply
            if len(results) >= MAX_CANDIDATES:
                break
    return list(results.values())


async def fetch_description(http, advertisement: Advertisement) -> Candidate | None:
    # Defense in depth: callers cannot bypass the parser's URL/origin validation.
    host = local_host(advertisement.host)
    description_url(advertisement.location, host)
    async with http.get(advertisement.location, allow_redirects=False) as response:
        if response.status != 200:
            return None
        if response.content_length is not None and response.content_length > MAX_DESCRIPTION:
            return None
        body = bytearray()
        async for chunk in response.content.iter_chunked(8192):
            body.extend(chunk)
            if len(body) > MAX_DESCRIPTION:
                return None
        return parse_description(bytes(body), advertisement)


async def discover(*, deadline: float, host: str | None = None) -> list[Candidate]:
    try:
        async with asyncio.timeout_at(deadline):
            replies = await advertisements(deadline=deadline, host=host)
            async with aiohttp.ClientSession(
                trust_env=False,
                auto_decompress=False,
                timeout=aiohttp.ClientTimeout(total=None),
            ) as http:
                candidates = []
                for reply in replies:
                    # One unreachable advertisement must not consume the entire scan.
                    try:
                        async with asyncio.timeout_at(
                            min(deadline, asyncio.get_running_loop().time() + 2)
                        ):
                            candidate = await fetch_description(http, reply)
                        if candidate is not None:
                            candidates.append(candidate)
                    except (aiohttp.ClientError, OSError, ValueError, TimeoutError):
                        continue
            # Conflicting names/models or UDN/address relationships are not candidates.
            unique = set(candidates)
            return sorted(
                [
                    c
                    for c in unique
                    if not any(
                        other != c and (other.host == c.host or other.udn == c.udn)
                        for other in unique
                    )
                ],
                key=lambda c: (c.udn, c.host),
            )
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    except (aiohttp.ClientError, OSError):
        raise AgentError(ErrorCode.NETWORK_ERROR) from None


async def inspect_certificate(host: str, *, deadline: float) -> str:
    """First-use inspection only. Sends no client key or application request.

    This deliberately unauthenticated handshake returns a fingerprint for local
    trust review. It must never be reused as an authenticated SSAP connection.
    """
    host = local_host(host)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    writer = None
    try:
        async with asyncio.timeout_at(deadline):
            _, writer = await asyncio.open_connection(host, 3001, ssl=context, server_hostname=host)
            tls = writer.get_extra_info("ssl_object")
            if tls is None:
                raise OSError
            cert = tls.getpeercert(binary_form=True)
            if not cert:
                raise OSError
            return hashlib.sha256(cert).hexdigest()
    except TimeoutError:
        raise AgentError(ErrorCode.TIMEOUT) from None
    except (OSError, ValueError):
        raise AgentError(ErrorCode.NETWORK_ERROR) from None
    finally:
        if writer is not None:
            # Abort the inspection-only transport; no TLS shutdown wait beyond deadline.
            writer.transport.abort()
