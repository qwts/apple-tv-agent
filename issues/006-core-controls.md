# 006: Implement navigation, playback, power and volume

GitHub: https://github.com/qwts/apple-tv-agent/issues/6
Status: in review
Priority: P0
Depends on: [005](005-session-status.md)

## Outcome

Execute ordinary TV actions once and report whether the effect was observed.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Map allowlisted remote actions to verified adapter methods; document home/menu semantics from issue 001 findings.
2. Implement capability-gated power on/off and volume up/down/set. Validate absolute levels before connecting and do not assume the audio route supports absolute volume.
3. Dispatch one requested action under the device lock. Do not substitute a toggle for explicit play/pause or power intent unless an independently verified state makes the operation correct and the design is updated.
4. Use bounded readback where supported to return confirmed versus sent. On transport loss after dispatch, return an error with unknown outcome and no automatic mutation retry.
5. Document connected-display/audio effects and capability limitations in the command reference.

## Acceptance criteria

- [x] Unsupported controls return structured errors without an alternative guessed action.
- [x] A dispatched action is never automatically duplicated after timeout/disconnect.
- [x] Confirmation is reported only when observed state matches the requested result.

## Validation

Test every action mapping, capability denial, boundary/NaN/infinite volume values, failure before/after dispatch, mismatched readback and no-retry behavior. Validate supported controls on the reference TV.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence (2026-09-07)

- Added an explicit 17-command allowlist in `controls.py`, runtime capability gates, and one-attempt mutation routing through the existing UUID lock and bounded owned session.
- Playback/power/volume use bounded state readback. Matching state confirms; missing/mismatched state remains sent. Step volume requires observed movement in the requested direction. Navigation/next/previous report sent.
- Every mutation failure is nonretryable, with not_sent before dispatch or unknown after possible dispatch, including cleanup failure and cancellation.
- `.venv/bin/python -m pytest -q`: **338 passed, 1 native-vault opt-in test skipped**. Coverage includes every mapping and capability denial, invalid/boundary levels, mismatched state and failures across connection/dispatch/readback/cleanup.
- Ruff, locked dependency sync/check, source/wheel builds and fresh installed-wheel checks under `python -O` passed. The controls guide is bundled and compared against source in wheel validation.
- Reference host macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: saved credentials returned real status and capabilities. The TV reported off/idle; an explicit play request returned FEATURE_UNAVAILABLE, outcome not_sent, retryable false and empty stderr.

Successful production control effects, physical Home/Menu semantics and Windows 11 hardware remain unverified release gates in issues 001/010. See [controls](../docs/controls.md) for mappings, connected display/audio effects and outcome limits. This change does not count an unavailable control as a successful playback hardware test.

### Review follow-up

Control-service construction failures now report not_sent and retryable false before any session starts, preserving native-vault error classification and recovery details. CLI regression tests cover vault initialization failure for all 17 controls. Local full suite: 355 passed, one opt-in native-vault test skipped.
