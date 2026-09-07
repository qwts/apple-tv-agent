# 010: Complete cross-platform CI and real-device release validation

GitHub: https://github.com/qwts/apple-tv-agent/issues/10
Status: open
Priority: P0
Depends on: [009](009-agent-skill.md)

## Outcome

Produce a reproducible, locally installable release candidate with evidence for the Mac/Windows promise.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Add macOS and Windows CI jobs for the supported Python matrix, lint, contract/unit/adapter tests, wheel build and clean-install smoke checks. Ordinary CI must not require a TV or secrets.
2. Provide an opt-in hardware test/runbook in docs/hardware-validation.md using isolated test data and explicit cleanup. Do not run control commands on real TVs in unattended CI.
3. Run the DESIGN.md hardware matrix from both native host OSes, recording exact versions and pass/fail/unsupported/not-tested evidence. Distinguish missing hardware from implementation defects.
4. Exercise upgrade/config compatibility, credential persistence across restart and local removal, wheel installation, skill installation and documented commands. Resolve failures or keep the issue open.
5. Update compatibility documentation and README support claims to match evidence. Build local artifacts and record reproduction commands; do not publish packages or create a remote repository as part of this issue.

## Acceptance criteria

- [x] CI passes on macOS and Windows from a clean checkout without LAN dependencies.
- [ ] Baseline discovery, pairing, status and pause/navigation pass on real Apple TV hardware from both host OSes before release is declared ready.
- [ ] Capability-dependent features have explicit results; missing hardware results remain not-tested and block unsupported compatibility claims.
- [ ] A fresh local installation follows README successfully and artifacts contain no private data.

## Validation

Run the full automated suite once per supported matrix entry, then the documented hardware checklist and install smoke tests. Attach sanitized evidence to the issue; retain open status if release gates remain unmet.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

## Implementation progress

The existing four-job CI matrix now covers the complete CLI and portable skill (448 tests passed, one opt-in skip per job in run 34141985450). Added [hardware runbook](../docs/hardware-validation.md) with dedicated OS-account isolation, full control/recovery matrix, upgrade checks, sanitized evidence and explicit cleanup. Added [release ledger](../docs/release-validation.md) with artifact reproduction commands and evidence boundaries.

Status remains **open**: no native Windows 11 test host is available in this session. Both-host hardware acceptance and the remaining Mac release matrix must be completed before release readiness. This documentation PR does not close the issue.
