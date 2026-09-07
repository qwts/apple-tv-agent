# 008: Add actionable local diagnostics and recovery guidance

GitHub: https://github.com/qwts/apple-tv-agent/issues/8
Status: open
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

- [ ] doctor defaults to local checks and does not mutate TV, firewall or network settings.
- [ ] Common failures include actionable next steps and report observations without unjustified certainty.
- [ ] Diagnostic artifacts contain no secret or typed-text sentinel.

## Validation

Test missing dependencies, locked vault, corrupt config, no network, empty scan and timeout using injected checks. Review instructions on both host OSes.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
