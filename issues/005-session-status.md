# 005: Implement bounded sessions, capabilities and status

Status: open
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

- [ ] Status distinguishes absent metadata, unsupported features and unreachable devices.
- [ ] Unavailable/unknown capability states do not become callable actions.
- [ ] Failures and cancellation release sessions and locks; retry never exceeds the deadline.

## Validation

Use adapter integration fakes to force connect/read/close failures, clock-controlled deadline exhaustion, partial metadata and simultaneous processes. Confirm real status from each validated host.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
