# Implementation issues

The implementation plans are maintained here and tracked as [GitHub issues](https://github.com/qwts/apple-tv-agent/issues). Keep local status/evidence and the corresponding hosted issue synchronized. Issue status and evidence are maintained in each file. P0 denotes a foundation or release gate; P1 work is also included in the planned release. Dependencies determine execution order, not priority alone.

| Issue | Priority | Depends on | Status |
| --- | --- | --- | --- |
| [001: Validate pyatv and cross-platform feasibility](001-transport-spike.md) | P0 | — | In progress |
| [002: Create the Python package and JSON CLI contract](002-package-contract.md) | P0 | 001 | Complete |
| [003: Implement discovery, durable identity and device selection](003-discovery-registry.md) | P0 | 002 | Complete |
| [004: Implement native credentials and interactive pairing](004-credentials-pairing.md) | P0 | 003 | In review |
| [005: Implement bounded sessions, capabilities and status](005-session-status.md) | P0 | 004 | Open |
| [006: Implement navigation, playback, power and volume](006-core-controls.md) | P0 | 005 | Open |
| [007: Implement installed-app launch and focused text input](007-apps-keyboard.md) | P1 | 006 | Open |
| [008: Add actionable local diagnostics and recovery guidance](008-diagnostics.md) | P1 | 005 | Open |
| [009: Author and package the portable Apple TV control skill](009-agent-skill.md) | P0 | 006, 007, 008 | Open |
| [010: Complete cross-platform CI and real-device release validation](010-validation-release.md) | P0 | 009 | Open |

Suggested sequence: 001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010. Issue 008 can start after 005 independently of control implementation.

For each issue, follow its implementation plan, validate acceptance criteria, and record evidence before changing its status and this index. If a dependency decision changes, update DESIGN.md and downstream issues together. Keep missing hardware/OS evidence explicit; finish independent work but do not mark an unmet release gate complete.

Agent handoff example:

> Implement issue 003 in issues/003-discovery-registry.md. Read DESIGN.md and completed dependency evidence first. Implement and validate all acceptance criteria, update documentation and issue status, and report any unmet criteria with the concrete blocker.

## GitHub tracking

- Issue 001: https://github.com/qwts/apple-tv-agent/issues/1
- Issue 002: https://github.com/qwts/apple-tv-agent/issues/2
- Issue 003: https://github.com/qwts/apple-tv-agent/issues/3
- Issue 004: https://github.com/qwts/apple-tv-agent/issues/4
- Issue 005: https://github.com/qwts/apple-tv-agent/issues/5
- Issue 006: https://github.com/qwts/apple-tv-agent/issues/6
- Issue 007: https://github.com/qwts/apple-tv-agent/issues/7
- Issue 008: https://github.com/qwts/apple-tv-agent/issues/8
- Issue 009: https://github.com/qwts/apple-tv-agent/issues/9
- Issue 010: https://github.com/qwts/apple-tv-agent/issues/10
