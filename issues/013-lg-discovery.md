# 013: Bounded LG discovery and certificate inspection

GitHub: https://github.com/qwts/apple-tv-agent/issues/24
Status: in review

Parent: #18. Depends on #22 (merged).

## Outcome
Implement bounded LG discovery and read-only TLS certificate inspection as the prerequisite for trusted registration. Do not create trust records or access credentials during discovery.

## Agent implementation plan
1. Parse bounded SSDP replies; require MediaRenderer advertisements, a local IPv4 sender and same-address HTTP description URL. Reject duplicate headers, redirects, credentials in URLs and off-device destinations.
2. Fetch bounded XML under the overall monotonic deadline, reject entity/DTD documents, select LG MediaRenderer identity and match UDN to the SSDP USN. Deduplicate identical observations and reject conflicting identities.
3. Add explicit read-only TLS certificate inspection on port 3001. Return SHA-256 fingerprint without sending application data; explain that inspection does not authenticate or approve trust.
4. Expose a separate experimental screen CLI with fixed JSON errors, finite timeout/input validation before networking, and no credentials/registration side effects. Keep baseline CLI unchanged.
5. Test synthetic SSDP/XML/HTTP/TLS cases, size bounds, redirects, cancellation, redaction and command validation. Package/check the entry point on macOS and Windows. Document privacy and remaining pairing/capture work.

## Acceptance criteria
- Discovery and inspection are bounded and perform no vault access.
- Untrusted discovery cannot redirect HTTP off the sender or silently become trusted registration.
- Failures return fixed structured errors without raw payloads or URLs.
- Offline tests and four-job CI pass; any hardware evidence is recorded separately.

## Evidence

Added `apple-tv-screen discover` and `inspect`, offline malformed-peer/origin/bounds/cancellation/CLI tests, direct declaration of the already locked aiohttp version, and wheel smoke checks for both entry points. On the reference Mac, multicast and targeted discovery each found one LG candidate and certificate inspection succeeded without registration or vault access. See [LG discovery documentation](../docs/lg-discovery.md). Native Windows LAN and production trusted pairing/capture remain untested and unimplemented respectively.

Local validation: 523 tests passed, one native-vault opt-in skip; Ruff lint/format passed; source/wheel builds and optimized-Python fresh hashed wheel checks passed, including both experimental entry points. Only aiohttp's direct dependency declaration changed; its locked version and transitive versions were preserved.
