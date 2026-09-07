# 001: Validate pyatv and cross-platform feasibility

GitHub: https://github.com/qwts/apple-tv-agent/issues/1
Status: in progress
Priority: P0
Depends on: None

## Outcome

Prove the proposed transport and native secret stores can support the design before freezing dependency and API choices.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Read the selected stable pyatv release source/API and record its version, Python requirements, license and install dependencies. Start with Python 3.12; document any justified change in DESIGN.md.
2. Build a small opt-in probe under tools/ that exercises discovery, pairing, connection, capabilities and pause/status through Python APIs. Do not persist credentials to upstream plaintext storage; keep them in memory for this probe.
3. Run installation and discovery probes on macOS and native Windows. Check available native keyring backends with disposable secrets and cleanup; record locked-store behavior.
4. With user-accessible hardware, verify required protocol pairing flows, feature mappings, stable identifiers, direct-host discovery, connection cleanup, and keyboard-focus APIs. Record actual signatures and protocol prerequisites for later issues.
5. Write docs/compatibility.md with exact environments, results, limitations and recommended dependency pin. Mark missing host/hardware tests blocked; document a concrete resolution path instead of claiming compatibility.

## Acceptance criteria

- [ ] A maintainer can reproduce the probes from documented macOS and PowerShell commands.
- [ ] The report identifies a tested release and the API mapping for each proposed operation, or clearly lists unresolved gates.
- [ ] Probe output contains no PIN, credential or entered text. Hardware/OS availability limitations are explicit.

## Validation

Run fresh virtual-environment installs on both OSes, a disposable native-vault round trip, and the opt-in reference-TV probe. Save sanitized observations, not raw protocol logs.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Current evidence (2026-09-07 UTC)

- Added [transport probe](../tools/transport_probe.py), pinned direct spike dependencies and [compatibility report](../docs/compatibility.md) with verified API mapping and both host OS runbooks.
- macOS 26.6.2 arm64 / Python 3.14.7: fresh dependency install passed; `pip check` passed; `python -m pytest -q`: **17 passed**.
- Native Keychain random-secret write/read/delete passed outside the execution sandbox; cleanup verified.
- Initial five-second LAN discovery returned zero candidates. After the user reported Little Snitch approval, a ten-second repeat found nine AirPlay devices, including two candidates offering AirPlay/Companion PIN pairing. Targeted discovery of the user-selected Apple TV 4K (second generation), tvOS 26.2, passed. AirPlay and Companion pairing passed; status/capabilities/focus read passed; pause was sent once and the user reported the TV paused afterwards. Added an explicit Play probe with capability checks and readback at the user's request.
- Corrected DESIGN.md and issue 003 to reject IPv6 because the selected transport's targeted scan accepts IPv4 only.
- Remaining gates: Windows host, locked-vault behavior and physical action semantics.

Issue remains in progress; the automated probe checks do not satisfy the hardware or cross-platform acceptance criteria.

- Resume follow-up: local Terminal re-pairing succeeded after a user-requested retry; user confirmed Play worked. No automatic mutation retry.

- Hosted CI: [run 34085123063](https://github.com/qwts/apple-tv-agent/actions/runs/34085123063) passed installation, dependency consistency, native backend selection and all 17 tests on macOS 26.6.2 arm64 and Windows Server 2025 AMD64, each with Python 3.12.10 and 3.14.7. Windows 11 hardware and native-vault write/read/delete remain unverified.

- PR review fix: track attempted playback dispatch per invocation. Errors before
  dispatch report `not_sent`; errors after dispatch starts report `unknown`.
  Regression coverage exercises Play/Pause through the CLI across discovery,
  pairing, connection, capability, dispatch, readback and cleanup failures. Local
  validation: `python -m pytest -q` — **30 passed**.
