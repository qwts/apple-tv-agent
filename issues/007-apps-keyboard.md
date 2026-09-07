# 007: Implement installed-app launch and focused text input

Status: open
Priority: P1
Depends on: [006](006-core-controls.md)

## Outcome

Support opening known apps and entering requested text where the device exposes keyboard focus.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Implement apps list and launch by exact installed app ID. Resolve display-name ambiguity in skill guidance rather than guessing; reject unknown IDs with useful details.
2. Refresh capabilities and installed-app membership before launch; do not accept arbitrary URL schemes or infer content search.
3. Implement keyboard type --text-stdin with UTF-8 validation, a 4096-byte bound, confirmed focus and capability checks. Preserve text verbatim and omit it from all results and diagnostics.
4. Apply the same locking, deadline, outcome and no-mutation-retry policy as core controls.
5. Document unavailable focus/keyboard behavior and app-specific limitations without promising visual UI access.

## Acceptance criteria

- [ ] Duplicate app names cannot select an arbitrary app and unknown IDs are rejected.
- [ ] Text is sent only to a confirmed focused input; unavailable/unknown focus fails before dispatch.
- [ ] Unicode and shell-like text are data, never executed, echoed or logged.

## Validation

Test duplicate apps, removed apps, unavailable focus, Unicode size limits, empty input policy, malicious-looking strings and post-dispatch timeout. Hardware-test launch and keyboard if exposed.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
