# 004: Implement native credentials and interactive pairing

GitHub: https://github.com/qwts/apple-tv-agent/issues/4
Status: in review
Priority: P0
Depends on: [003](003-discovery-registry.md)

## Outcome

Pair once per host and persist reusable credentials without exposing them to the agent or repository.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Implement a credential-store adapter selecting validated macOS Keychain or Windows Credential Manager backends; reject plaintext/unknown backends and translate locked/unavailable store failures.
2. Integrate in-memory pyatv settings with secret lookup by device UUID/protocol, preventing automatic serialization of credentials into registry files.
3. Implement one-process interactive pairing with hidden PIN entry, required protocol detection, handler lifetime, deadlines, cancellation and at most three attempts per protocol. Non-TTY use returns INTERACTIVE_REQUIRED.
4. Verify pairing before secret persistence, preserve prior valid credentials on failed re-pairing, and report per-protocol partial success or storage failure accurately.
5. Implement devices forget with idempotent partial-deletion recovery, default cleanup and clear local-removal semantics. Ensure authentication failure does not automatically start pairing.

## Acceptance criteria

- [x] A new CLI process reconnects using the native vault after successful pairing.
- [x] PINs and credentials never appear in CLI arguments, output, logs, registry, fixtures or committed artifacts.
- [x] Noninteractive pairing exits promptly; failed/canceled pairing releases resources and does not claim success.
- [x] Forgetting one TV leaves other TVs intact and reports vault deletion failures.

## Validation

Test fake-vault failures and partial pairing plus opt-in isolated native-backend round trips on both OSes. Exercise invalid PIN, timeout, Ctrl-C, re-pairing and restart on hardware when available.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence (2026-09-07)

- Added native-only credential storage with UUID/protocol namespacing, verified write/readback, rollback on failed overwrite, and idempotent deletion. Unknown/plaintext/chained backends are rejected.
- Added hidden cancellable local PIN input; handler lifetime/cleanup, 120-second attempts (at most three), protocol verification before persistence, per-device locks, partial-result errors and registry bookkeeping. No automatic reconnect-to-pairing fallback.
- Added explicit AirPlay Pair-Verify and owned Companion/MRP setup handles so partial connection failures can be cleaned up; pyatv settings remain memory-only and are hydrated after identity checks.
- Added coordinated `devices forget`, preserving registry/default on partial vault failure and permitting UUID retries after registry removal. Other devices remain isolated.
- **224 tests pass, 1 opt-in native test skipped** in the ordinary local suite. Cases include synthetic vault failures/rollback, partial pairing, canceled input, attempt limits, handler/connection cleanup, identity-before-vault ordering, secret log suppression and partial deletion recovery.
- Opt-in macOS native Keychain test: **1 passed**, including a separate-process read and verified cleanup of an isolated random credential.
- Live reference-TV validation on macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: hidden local-terminal AirPlay and Companion pairing both passed. Credentials persisted in Keychain. A fresh Python process authenticated both protocols from the vault; reconnect was repeated successfully after cleanup changes. No playback/navigation commands were sent. PINs and credential values were not saved in output or repository artifacts.
- Source/wheel build, locked dependency consistency and fresh-wheel checks under `python -O` passed; bundled registry/pairing guides were verified against their sources.

The acceptance checks above have macOS hardware and deterministic failure-path evidence. Native Windows vault operations and Windows 11 TV pairing/restart, real invalid-PIN/locked-vault recovery, and remaining physical controls are not claimed tested; Windows hardware/native-vault release gates remain in issue 001. CI runs the fake-backed suite on both OSes and explicitly skips native vault mutation.

See [pairing and recovery](../docs/pairing.md) and the opt-in [reconnect tool](../tools/verify_pairing.py).

### Review follow-up

Preserve completed vault-deletion details and UUID recovery when registry removal times out or is canceled. The CLI retains those details while classifying its own expired deadline as `TIMEOUT`. Regression tests use a contended registry lock, exercise task cancellation and timeout, and verify UUID retry clears the retained default. Local suite: **227 passed, 1 native-vault test skipped**.
