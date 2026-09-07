# 005: Implement bounded sessions, capabilities and status

GitHub: https://github.com/qwts/apple-tv-agent/issues/5
Status: in review
Priority: P0
Depends on: [004](004-credentials-pairing.md)

## Outcome

Connect to a selected TV and expose truthful state and capabilities with reliable cleanup.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Implement adapter connection hydration after identity verification and credential lookup, with per-device cross-process locking.
2. Apply a single overall deadline to normal command work and close/await library cleanup on every exit path; map cancellation and busy-device behavior consistently.
3. Normalize feature availability into the design states using the selected release API. Implement capabilities and partial status with nulls, reasons and observation timestamps.
4. Translate authentication, connectivity, timeout and protocol failures to public errors. Allow at most one safe read retry within the same deadline.
5. Add structured redaction at logging boundaries and avoid raw library-object serialization.

## Acceptance criteria

- [x] Status distinguishes absent metadata, unsupported features and unreachable devices.
- [x] Unavailable/unknown capability states do not become callable actions.
- [x] Failures and cancellation release sessions and locks; retry never exceeds the deadline.

## Validation

Use adapter integration fakes to force connect/read/close failures, clock-controlled deadline exhaustion, partial metadata and simultaneous processes. Confirm real status from each validated host.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence (2026-09-07)

- Implemented status/capabilities services with explicit/default/sole selection, per-device locks, registry reread after lock acquisition, identity-before-vault checks and in-memory connection hydration.
- A shared monotonic deadline includes cleanup; work reserves up to one second for closing. At most one transient read retry uses the original deadline. Authentication/protocol/cleanup failures do not retry; mutation commands are rejected by this read-only service.
- The adapter retains every pyatv protocol setup close handle before connecting, closes completed/partial setups once, closes HTTP resources and waits for cleanup. Unknown/unavailable features remain nonavailable; keyboard type additionally requires focus.
- Status emits UTC observations, nullable metadata and fixed per-field reasons. Native-vault and protocol exception text never enters error output, and credential-bearing library logs are suppressed throughout the session.
- Local suite: **250 passed, 1 native-vault opt-in test skipped**. Tests include safe retry/deadline preservation, cancellation/cleanup failures, an actual second process holding the device lock, protocol error translation, missing/invalid metadata and identity mismatch before vault access.
- macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: the saved reference-TV credentials produced successful fresh-process `status` and `capabilities` JSON with empty stderr. Playback state was `playing`. No re-pairing or control command was used.
- Locked dependency checks, Ruff, source/wheel builds and fresh wheel checks under `python -O` passed. Wheel smoke tests use unimplemented `doctor` for deterministic unavailable errors, so they do not contact local devices. Recovery/session guides are bundled and checked against source contents.

Windows CI validates simulated sessions and cross-process locking; Windows 11 TV/native-vault hardware status checks remain issue 001 release gates. See [session semantics](../docs/sessions.md).

### Review follow-up

Corrected keyboard typing capability to `TextAppend`, matching the documented append semantics. Regression tests distinguish append-only and replacement-only support, including unavailable/unknown append states with confirmed focus.
