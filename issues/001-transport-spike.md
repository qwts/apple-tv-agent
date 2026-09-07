# 001: Validate pyatv and cross-platform feasibility

Status: open
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
