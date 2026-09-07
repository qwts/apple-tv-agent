# 008: Add actionable local diagnostics and recovery guidance

GitHub: https://github.com/qwts/apple-tv-agent/issues/8
Status: in review
Priority: P1
Depends on: [005](005-session-status.md)

## Outcome

Help a user distinguish setup, pairing and LAN failures without leaking credentials or changing network settings.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Implement doctor for runtime versions, selected native keyring availability, registry readability and executable context. Keep network activity behind --network.
2. For network diagnostics, report observed scan/reachability results and bounded failure reasons without claiming to diagnose a firewall from an empty scan alone.
3. Write docs/troubleshooting.md covering macOS local-network access, Windows firewall/private-network configuration, VPN/guest-network isolation, direct-host fallback, locked vaults and re-pairing. Verify OS-specific instructions against current primary documentation during implementation.
4. Redact sensitive fields by construction and test with sentinel secrets. Offer explicit local diagnostic detail options only where useful; never dump credentials or entered text.
5. Give error-specific next steps and preserve structured output/exit rules.

## Acceptance criteria

- [x] doctor defaults to local checks and does not mutate TV, firewall or network settings.
- [x] Common failures include actionable next steps and report observations without unjustified certainty.
- [x] Diagnostic artifacts contain no secret or typed-text sentinel.

## Validation

Test missing dependencies, locked vault, corrupt config, no network, empty scan and timeout using injected checks. Review instructions on both host OSes.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence (2026-09-07)

- Added DoctorService with dependency versions/import checks, interpreter/host/environment context, exact native-backend selection, registry readability and conservative pairing-marker observations. Default doctor never constructs a network adapter and never reads/writes credentials.
- `--network` performs only bounded discovery and reports candidate counts, empty results, timeout or transport failure without claiming firewall diagnosis. A completed diagnostic report exits 0; individual health checks retain pass/fail/not_tested. CLI deadline/parser failures keep the existing error contract.
- Added bundled [troubleshooting guidance](../docs/troubleshooting.md), verified against current Apple/Microsoft primary documentation. Missing foundational imports that prevent CLI startup require environment recovery outside doctor.
- `.venv/bin/python -m pytest -q`: **366 passed, 1 native-vault opt-in test skipped**. Tests cover local-only behavior, missing/broken dependencies, vault selection failure without access claims, corrupt-registry preservation, network timeout/empty/error and sentinel redaction.
- Ruff, locked dependency sync/check, source/wheel builds and fresh installed-wheel checks under `python -O` passed. Wheel entry-point checks now exercise implemented local doctor; deterministic error tests use an invalid remote action.
- Live macOS 26.6.2 arm64 / Python 3.14.7: local doctor and explicit network doctor completed with empty stderr. Local backend/registry checks passed; vault access remained not_tested. Network doctor observed Apple TV discovery responses without pairing or controls.

Windows hardware/vault recovery remains unverified in issues 001/010. The independent optional LG capture spike and follow-up issue 011 record observed HDMI screenshots without extending baseline support or committing private captures.

### Review follow-up

Doctor now reports a failed dependency check for importable versions that differ from the exact runtime pins, with installed/required versions and locked-install recovery guidance. Regression coverage checks older/newer/prerelease mismatches for every runtime dependency and verifies that diagnostic pins match pyproject.toml.
