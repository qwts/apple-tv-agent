# Implementation issues

The implementation plans are maintained here and tracked as [GitHub issues](https://github.com/qwts/apple-tv-agent/issues). Keep local status/evidence and the corresponding hosted issue synchronized. Issue status and evidence are maintained in each file. P0 denotes a foundation or release gate; P1 work is also included in the planned release. Dependencies determine execution order, not priority alone.

| Issue | Priority | Depends on | Status |
| --- | --- | --- | --- |
| [001: Validate pyatv and cross-platform feasibility](001-transport-spike.md) | P0 | — | In progress |
| [002: Create the Python package and JSON CLI contract](002-package-contract.md) | P0 | 001 | Complete |
| [003: Implement discovery, durable identity and device selection](003-discovery-registry.md) | P0 | 002 | Complete |
| [004: Implement native credentials and interactive pairing](004-credentials-pairing.md) | P0 | 003 | Complete |
| [005: Implement bounded sessions, capabilities and status](005-session-status.md) | P0 | 004 | Complete |
| [006: Implement navigation, playback, power and volume](006-core-controls.md) | P0 | 005 | Complete |
| [007: Implement installed-app launch and focused text input](007-apps-keyboard.md) | P1 | 006 | Complete |
| [008: Add actionable local diagnostics and recovery guidance](008-diagnostics.md) | P1 | 005 | Complete |
| [009: Author and package the portable Apple TV control skill](009-agent-skill.md) | P0 | 006, 007, 008 | In review |
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

## Optional follow-up

[011: Paired LG screen observation](011-lg-screen-observation.md), tracked as [GitHub #18](https://github.com/qwts/apple-tv-agent/issues/18), builds on the successful HDMI screenshot experiment. It is outside the baseline Apple TV release and includes an implementation plan for pairing, image handling, privacy and visual navigation.

[012: Observation provider contract](012-observation-contract.md), tracked as [GitHub #22](https://github.com/qwts/apple-tv-agent/issues/22), defines the typed boundary and trust requirements before implementing the LG provider. Status: in review.

[013: LG discovery and certificate inspection](013-lg-discovery.md), tracked as [GitHub #24](https://github.com/qwts/apple-tv-agent/issues/24), implements the read-only prerequisite to trusted pairing. Status: in review.

[014: Trusted LG pairing](014-lg-pairing.md), tracked as [GitHub #26](https://github.com/qwts/apple-tv-agent/issues/26), implements local certificate/permission approval, native credential persistence, reconnect verification and local removal.

[015: LG capture, binding and skill integration](015-lg-capture.md), tracked as [GitHub #28](https://github.com/qwts/apple-tv-agent/issues/28), completes the optional provider implementation. Status: in review; reference Mac capture/deletion passed, native Windows hardware validation remains open.

[016: Versioned GitHub release bundles](016-release-pipeline.md), tracked as [GitHub #30](https://github.com/qwts/apple-tv-agent/issues/30), plans downloadable macOS, Windows and Linux distributions, secure Linux credential support, release automation and platform validation. Status: open.
