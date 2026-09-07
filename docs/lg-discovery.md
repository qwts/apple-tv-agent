# Experimental LG discovery and certificate inspection

The separate `apple-tv-screen` executable is a read-only prerequisite for optional LG observation. It supports **discover** and **inspect**, plus [trusted pairing and local credential management](lg-pairing.md). Capture and skill integration are still pending under [issue 18](https://github.com/qwts/apple-tv-agent/issues/18). The Apple TV CLI is unchanged. The discovery and inspection commands documented here do not read the native vault, save registrations or send remote controls.

Install using the repository's locked environment and invoke its absolute executable path, as with `apple-tv-agent`. Examples below abbreviate that path. The same commands work in PowerShell when invoked with `&` and the quoted executable path.

```text
apple-tv-screen discover --timeout 15
apple-tv-screen discover --host 192.168.1.10 --timeout 15
apple-tv-screen inspect --host 192.168.1.10 --timeout 15
```

Replace the example address with the selected TV's actual local IPv4 address. `--host` sends SSDP to that one address on port 1900; it does not sweep a subnet or bypass filtering. Without it, discovery sends one MediaRenderer M-SEARCH to the SSDP multicast address. Allow any local firewall prompt, then retry discovery explicitly. Empty candidates is a successful scan, not a diagnosis of firewall or TV state. Discovery selects the default OS route; multi-interface selection is not implemented.

## Bounds and untrusted identity

One monotonic timeout (1–120 seconds, default 15) covers the operation. Discovery collects replies for up to two seconds, examines at most 128 packets of at most 8192 bytes, and fetches at most 32 advertised descriptions with a two-second per-description cap within that overall budget. It rejects malformed/duplicate headers, off-sender description URLs, redirects, nonliteral/public/loopback/multicast addresses, non-HTTP descriptions, userinfo and URL fragments. HTTP proxy environment settings and automatic decompression are disabled. Description ports must be valid, but are not presumed to be port 80.

The full description body is capped at 64 KiB. Only UTF-8 XML without DTD/entity declarations is accepted. The root MediaRenderer's LG manufacturer and UDN must match the advertisement; conflicting address/UDN/name/model observations are omitted. Names/model strings are untrusted display data. Discovery origin/UDN matching prevents accidental cross-device URL following; it does not cryptographically authenticate a UDP sender or a manufacturer claim. Spoofed advertisements remain possible. Returned candidates contain private addresses and identifiers: inspect locally and do not commit raw results.

`inspect` performs an **unauthenticated first-use TLS handshake** to the chosen address on port 3001, hashes the peer's DER certificate with SHA-256, then aborts the inspection transport. It sends no application data, SSAP registration or client key. The result always says `trusted: false`; displaying a fingerprint is not trust approval. The future pairing flow must show the identity/fingerprint for explicit local trust acceptance and pin subsequent connections before credential reuse. Never use this inspection connection as an authenticated connection. Inspecting an arbitrary address does not establish that it is an LG TV.

## Experimental JSON contract

Both commands emit one JSON object to stdout; stderr is empty for normal results/errors. `--help` is a human-readable exception. The independent discovery envelope contains `schema_version: 1`, `command` (`discover`, `inspect`, or null if parsing failed), `ok`, `data` and `error`. It is not the baseline Apple TV response schema or the image observation schema.

- Successful discovery data: `candidates`, a list of `{host, udn, name, model}`. Nothing is registered implicitly.
- Successful inspection data: `{host, port: 3001, certificate_sha256, trusted: false}`.
- Failure data is null; `error` contains a fixed `code` and `message`, never raw XML, URLs, peer messages or exception text. Exit codes: 2 invalid arguments, 5 network/deadline failure, 1 unexpected failure/cancellation. Success exits 0. Invalid commands/arguments fail before networking.

Unreachable or malformed individual description responses are skipped; a completed scan may therefore return fewer candidates, including zero. Overall deadline exhaustion returns TIMEOUT. A discovered fingerprint and a later pairing certificate must be compared during explicit trust establishment, not inferred from IP equality.

## Validation

Synthetic tests cover malformed/oversized SSDP and XML, mismatched identities, duplicate headers, off-device/credential-bearing URLs, redirects, chunked bodies, cancellation cleanup, conflicts, TLS inspection without application writes, fixed errors and validation before network dispatch. CI tests both experimental entry points from a clean wheel without LAN access. Native Windows 11 LAN and LG hardware tests remain separate compatibility gates.

The existing pinned aiohttp transport dependency is now declared directly because this module imports it. No dependency version was intentionally upgraded for discovery. The discovery module has no import-time network activity and requires no LG hardware for base installation.

### Reference Mac observation (2026-09-07)

On macOS 26.6.2 arm64 / Python 3.14.7, targeted and multicast discovery each returned one candidate for the previously identified reference LG and retrieved a matching MediaRenderer advertisement and XML. Its description reports generic model `LG TV` and manufacturer `LG Electronics.`; the trailing-period spelling is covered by a regression fixture. An inspection-only TLS handshake on port 3001 returned a SHA-256 fingerprint and `trusted: false`. No registration, vault access, screenshot or TV control was performed. This is discovery/certificate-read evidence, not authenticated pairing or Windows hardware support.
