# 006: Implement navigation, playback, power and volume

GitHub: https://github.com/qwts/apple-tv-agent/issues/6
Status: open
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

- [ ] Unsupported controls return structured errors without an alternative guessed action.
- [ ] A dispatched action is never automatically duplicated after timeout/disconnect.
- [ ] Confirmation is reported only when observed state matches the requested result.

## Validation

Test every action mapping, capability denial, boundary/NaN/infinite volume values, failure before/after dispatch, mismatched readback and no-retry behavior. Validate supported controls on the reference TV.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
