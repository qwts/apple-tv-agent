# 014: Trusted LG pairing and native credential lifecycle

GitHub: https://github.com/qwts/apple-tv-agent/issues/26
Status: in review

Parent #18; depends on #24 and #22.

## Outcome
Pair an explicitly selected LG through local certificate/permission approval and a pinned SSAP connection. Persist native credentials and separate LG registration, then verify reconnect and support recoverable local removal.

## Agent implementation plan
1. Add a versioned atomic LG registry with UUID, advertised identity, address, certificate fingerprint and pairing marker. Never overwrite changed identity/certificate silently.
2. Reuse native-only vault validation and verified write/rollback/delete behavior in a distinct LG service namespace.
3. Bundle the known working public manifest with upstream license/provenance; disclose broad permissions during local pairing. Connect using SHA-256 certificate pinning, reject redirects and bound messages/deadlines. Load saved credentials only after identity and certificate validation.
4. Implement pair, devices, verify and forget on the experimental CLI. Pairing requires a real local terminal, bounded trust prompt and TV approval. Verify sends only registration plus an allowlisted read. Failures/cancellation produce fixed JSON with no key/raw SSAP payload. Retain recoverable registry records after partial failures.
5. Test trust changes, identity mismatch, no-secret-before-pin ordering, malformed SSAP/permissions, vault isolation, registry preservation/removal and noninteractive refusal. Run package/CI checks; document local approval and hardware limitations. HDMI binding and image capture remain follow-up work under #18.

## Acceptance criteria
- No credential is reused before pinned connection and matching discovery identity.
- Pairing success requires authenticated read and verified native-vault storage.
- Local removal is idempotent/recoverable and never claims TV-side revocation.
- Cross-platform offline CI passes; actual pairing requires local approval and hardware evidence remains explicit.

## Evidence

Implemented separate atomic LG trust registry, native-vault namespace with verified writes/deletion, pinned SSAP with redirect rejection/read allowlist, local trust/permission prompt and pair/devices/verify/forget commands. Manifest/license provenance and recovery are documented in [LG pairing](../docs/lg-pairing.md).

Mac hardware pairing and a separate-process production verify succeeded with local user approval and saved Keychain credentials. The isolated native LG vault fresh-process/read/delete test passed. Windows hardware, HDMI bindings and capture remain follow-up work; the reference pairing is retained.

Validation: Ruff lint/format; 554 tests passed with two native-vault opt-in skips; isolated LG native test passed separately; source/wheel build and fresh hashed wheel checks include the manifest, license and pairing guide.
