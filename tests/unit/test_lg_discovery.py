"""Offline malformed-peer, origin, bounded-body, cancellation and CLI tests."""

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation import cli
from apple_tv_agent.observation import discovery as lg

HOST = "192.168.1.10"
UDN = "uuid:01234567-89ab-cdef-0123-456789abcdef"
URL = f"http://{HOST}:1234/device.xml"
AD = lg.Advertisement(HOST, UDN, URL)
XML = f"""<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>{lg.SERVICE}</deviceType><manufacturer>LG Electronics</manufacturer>
<UDN>{UDN}</UDN><friendlyName>Test TV</friendlyName><modelName>Test Model</modelName>
</device></root>""".encode()


def packet(url=URL):
    return (
        f"HTTP/1.1 200 OK\r\nST: {lg.SERVICE}\r\nUSN: {UDN}::{lg.SERVICE}\r\n"
        f"LOCATION: {url}\r\n\r\n"
    ).encode()


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "0.0.0.0", "224.0.0.1", "8.8.8.8", "::1", "tv.local", "192.168.1.10/24"]
)
def test_reject_nonlocal_or_nonliteral_host(host):
    with pytest.raises(AgentError):
        lg.local_host(host)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.11/device.xml",
        "http://tv.local/device.xml",
        f"http://user:secret@{HOST}/device.xml",
        f"https://{HOST}/device.xml",
        f"http://{HOST}:0/device.xml",
        f"http://{HOST}:99999/device.xml",
        f"http://{HOST}/device.xml#fragment",
        f"http://{HOST}/bad\npath",
        f"http://{HOST}\\@192.168.1.11/",
        "file:///etc/passwd",
    ],
)
def test_reject_unsafe_description_locations(url):
    assert lg.parse_reply(packet(url), HOST) is None


def test_packet_bounds_and_duplicate_headers():
    assert lg.parse_reply(packet(), HOST) == AD
    assert lg.parse_reply(packet() + b"x" * lg.MAX_PACKET, HOST) is None
    assert (
        lg.parse_reply(
            packet().replace(b"\r\n\r\n", b"\r\nLOCATION: " + URL.encode() + b"\r\n\r\n"), HOST
        )
        is None
    )
    assert lg.parse_reply(packet().replace(b"200 OK", b"302 Found"), HOST) is None
    assert lg.parse_reply(b"\xff", HOST) is None
    assert lg.parse_reply(packet().replace(b"LOCATION:", b" LOCATION:"), HOST) is None


@pytest.mark.parametrize(
    "raw",
    [
        XML.replace(UDN.encode(), b"uuid:11111111-1111-1111-1111-111111111111"),
        XML.replace(b"LG Electronics", b"Other Manufacturer"),
        XML.replace(b"</device>", b"<UDN>duplicate</UDN></device>"),
        b'<!DOCTYPE root [<!ENTITY e "expansion">]>' + XML,
        XML.decode().encode("utf-16"),
        XML[:80],
        b"x" * (lg.MAX_DESCRIPTION + 1),
    ],
    ids=["wrong-udn", "wrong-maker", "duplicate-udn", "dtd", "utf16", "truncated", "oversized"],
)
def test_untrusted_xml(raw):
    assert lg.parse_description(raw, AD) is None


def test_description_identity():
    assert lg.parse_description(XML, AD) == lg.Candidate(HOST, UDN, "Test TV", "Test Model")


class Response:
    def __init__(self, chunks, status=200, length=None):
        self.chunks = chunks
        self.status = status
        self.content_length = length
        self.content = self
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk


class HTTP:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.mark.parametrize(
    "chunks,status,length,valid",
    [
        ([XML[:7], XML[7:]], 200, None, True),
        ([XML], 302, None, False),
        ([b"x" * 40000, b"x" * 40000], 200, None, False),
        ([XML], 200, lg.MAX_DESCRIPTION + 1, False),
    ],
)
def test_full_stream_and_limits(chunks, status, length, valid):
    response = Response(chunks, status, length)
    http = HTTP(response)
    result = asyncio.run(lg.fetch_description(http, AD))
    assert (result is not None) == valid
    assert http.calls == [(URL, {"allow_redirects": False})]
    assert response.closed


def test_cancel_closes_response():
    response = Response([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(lg.fetch_description(HTTP(response), AD))
    assert response.closed


def test_fetch_rechecks_origin():
    http = HTTP(Response([XML]))
    with pytest.raises(ValueError):
        asyncio.run(lg.fetch_description(http, lg.Advertisement(HOST, UDN, "http://192.168.1.11/")))
    assert not http.calls


@pytest.mark.parametrize(
    "argv",
    [
        ["inspect"],
        ["pair"],
        ["discover", "--timeout", "nan"],
        ["discover", "--timeout", "0"],
        ["inspect", "--host", "tv.local"],
    ],
)
def test_cli_validates_before_dispatch(argv, monkeypatch, capsys):
    dispatch = AsyncMock()
    monkeypatch.setattr(cli, "dispatch", dispatch)
    assert cli.main(argv) == 2
    dispatch.assert_not_called()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["error"]["code"] == "INVALID_ARGUMENT"


def test_cli_redacts_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "dispatch", AsyncMock(side_effect=OSError("PRIVATE URL AND KEY")))
    assert cli.main(["discover"]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    assert json.loads(captured.out)["data"] is None


def test_certificate_inspection_has_no_application_writes(monkeypatch):
    class TLS:
        def getpeercert(self, *, binary_form):
            assert binary_form
            return b"synthetic-certificate"

    class Writer:
        transport = None
        aborted = False

        def get_extra_info(self, name):
            assert name == "ssl_object"
            return TLS()

        def abort(self):
            self.aborted = True

    writer = Writer()
    writer.transport = writer
    connect = AsyncMock(return_value=(None, writer))
    monkeypatch.setattr(lg.asyncio, "open_connection", connect)

    async def run():
        return await lg.inspect_certificate(HOST, deadline=asyncio.get_running_loop().time() + 1)

    assert asyncio.run(run()) == hashlib.sha256(b"synthetic-certificate").hexdigest()
    assert writer.aborted
    assert connect.call_args.args == (HOST, 3001)


def test_certificate_failure_is_fixed(monkeypatch):
    monkeypatch.setattr(lg.asyncio, "open_connection", AsyncMock(side_effect=OSError("PRIVATE")))

    async def run():
        return await lg.inspect_certificate(HOST, deadline=asyncio.get_running_loop().time() + 1)

    with pytest.raises(AgentError) as error:
        asyncio.run(run())
    assert error.value.code == ErrorCode.NETWORK_ERROR
    assert "PRIVATE" not in str(error.value)


def test_conflicting_identities_removed(monkeypatch):
    monkeypatch.setattr(lg, "advertisements", AsyncMock(return_value=[AD, AD, AD]))
    one = lg.Candidate(HOST, UDN, "one", "model")
    two = lg.Candidate(HOST, UDN, "two", "model")
    monkeypatch.setattr(lg, "fetch_description", AsyncMock(side_effect=[one, one, two]))

    async def run():
        return await lg.discover(deadline=asyncio.get_running_loop().time() + 1)

    assert asyncio.run(run()) == []


def test_reference_lg_manufacturer_punctuation():
    raw = XML.replace(b"LG Electronics", b"LG Electronics.")
    assert lg.parse_description(raw, AD) is not None


def test_expired_deadline_closes_discovery(monkeypatch):
    async def blocked(**kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(lg, "advertisements", blocked)

    async def run():
        return await lg.discover(deadline=asyncio.get_running_loop().time() - 1)

    with pytest.raises(AgentError) as error:
        asyncio.run(run())
    assert error.value.code == ErrorCode.TIMEOUT


@pytest.mark.parametrize("error", [asyncio.CancelledError(), KeyboardInterrupt()])
def test_cli_cancellation_keeps_json_envelope(error, monkeypatch, capsys):
    monkeypatch.setattr(cli, "dispatch", AsyncMock(side_effect=error))
    assert cli.main(["discover"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["error"]["code"] == "INTERNAL_ERROR"


def test_help_still_exits_successfully(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_missing_tls_metadata_is_network_error_and_aborts(monkeypatch):
    from unittest.mock import Mock

    writer = Mock()
    writer.get_extra_info.return_value = None
    monkeypatch.setattr(lg.asyncio, "open_connection", AsyncMock(return_value=(None, writer)))

    async def run():
        return await lg.inspect_certificate(HOST, deadline=asyncio.get_running_loop().time() + 1)

    with pytest.raises(AgentError) as error:
        asyncio.run(run())
    assert error.value.code == ErrorCode.NETWORK_ERROR
    writer.transport.abort.assert_called_once_with()
