# 004: Implement native credentials and interactive pairing

GitHub: https://github.com/qwts/apple-tv-agent/issues/4
Status: open
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

- [ ] A new CLI process reconnects using the native vault after successful pairing.
- [ ] PINs and credentials never appear in CLI arguments, output, logs, registry, fixtures or committed artifacts.
- [ ] Noninteractive pairing exits promptly; failed/canceled pairing releases resources and does not claim success.
- [ ] Forgetting one TV leaves other TVs intact and reports vault deletion failures.

## Validation

Test fake-vault failures and partial pairing plus opt-in isolated native-backend round trips on both OSes. Exercise invalid PIN, timeout, Ctrl-C, re-pairing and restart on hardware when available.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
