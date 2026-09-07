# 012: Define optional screen-observation provider contract

GitHub: https://github.com/qwts/apple-tv-agent/issues/22
Status: in review

Parent: #18

## Outcome
Define the optional screen-observation contract before adding LG network access. Keep the baseline Apple TV CLI and response schema unchanged.

## Agent implementation plan
1. Add typed, immutable models for an explicit Apple TV / LG / HDMI binding and a versioned observation result. Represent local image metadata, timing, input context and insufficient evidence without credentials or image URLs.
2. Define an asynchronous provider interface with a shared monotonic deadline. Specify TLS trust before credential reuse, bounded identity discovery, native-vault separation and artifact ownership in the design.
3. Require fresh observations of the bound input before treating an image as usable context. Separate visual inference from Apple TV command confirmation; no automatic controls or screenshot loop.
4. Generate and package a separate observation schema. Test invalid bindings, invalid image metadata, input mismatch, temporal boundaries, and schema/package inclusion without LAN or vault access.
5. Document subsequent discovery/pairing and bounded-capture work under #18. Do not expose an unimplemented CLI command or claim production capture support.

## Acceptance criteria
- Contract and trust rules are reviewable without hardware.
- Invalid/unusable observations cannot pass the context-eligibility helper.
- Independent schema is included in wheel and source distribution and validated in CI.
- Baseline CLI tests continue passing; #18 remains open for implementation and hardware validation.

## Evidence

Added immutable binding/image/observation models, freshness/input eligibility, asynchronous provider and owned-artifact discard interfaces, and a separately generated/bundled v1 schema. [Provider design](../docs/observation-contract.md) specifies trust, permissions, retention and follow-up implementation. Local Ruff checks/formatting pass; 477 tests pass with one native-vault opt-in skip. Source/wheel build and clean hashed wheel installation pass, including bundled observation-schema equality. No network/vault/TV operations were performed.
