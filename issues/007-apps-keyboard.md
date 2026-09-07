# 007: Implement installed-app launch and focused text input

GitHub: https://github.com/qwts/apple-tv-agent/issues/7
Status: in review
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

- [x] Duplicate app names cannot select an arbitrary app and unknown IDs are rejected.
- [x] Text is sent only to a confirmed focused input; unavailable/unknown focus fails before dispatch.
- [x] Unicode and shell-like text are data, never executed, echoed or logged.

## Validation

Test duplicate apps, removed apps, unavailable focus, Unicode size limits, empty input policy, malicious-looking strings and post-dispatch timeout. Hardware-test launch and keyboard if exposed.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence (2026-09-07)

- Added `apps_keyboard.py` for typed app-list normalization, exact installed bundle-ID launch and focused TextAppend. Duplicate names are retained for explicit selection; unknown IDs and URL schemes fail before dispatch. Launch refreshes capabilities after retrieving the list.
- Keyboard input preserves UTF-8 bytes as text, requires confirmed focus and TextAppend, and never reads text back or includes it in results. Both mutations report sent on transport completion, not visual confirmation.
- Integrated app listing into bounded safe-read retry; app launch/keyboard use the existing lock/deadline/no-mutation-retry and initialization/dispatch outcome handling.
- `.venv/bin/python -m pytest -q`: **391 passed, 1 native-vault opt-in test skipped**. Coverage includes duplicate/removed apps, malformed lists, capability changes, focus denial, Unicode byte boundaries, shell-like data, redaction, constructor errors, and failures/cancellation before and after dispatch.
- Ruff, locked dependency sync/check, source/wheel builds and fresh installed-wheel checks under `python -O` passed. The new [apps/keyboard guide](../docs/apps-keyboard.md) is bundled and checked against source.
- Reference macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: saved credentials returned 28 launchable apps. One exact installed Netflix launch completed with sent and no stderr. Visible launch effect was not independently confirmed.

Intentional focused-field keyboard typing and Windows 11 hardware remain untested release gates in issues 001/010. No keyboard text was sent to the reference TV in this run.

### Review follow-up

Launch capability now requires both LaunchApp and AppList; missing app IDs and URL/path-shaped IDs have distinct reasons. Regression tests cover all capability-state combinations and input error reasons.
