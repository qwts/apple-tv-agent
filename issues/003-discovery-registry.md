# 003: Implement discovery, durable identity and device selection

GitHub: https://github.com/qwts/apple-tv-agent/issues/3
Status: in review
Priority: P0
Depends on: [002](002-package-contract.md)

## Outcome

Find local TVs and reliably target the intended registered device across address changes.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Implement bounded scan and literal-address targeted discovery through the adapter; normalize candidates without writing credentials or changing defaults.
2. Implement versioned nonsecret registry with platformdirs, atomic replacement and cross-platform locking. Validate corrupt/unknown schemas with actionable errors; do not silently discard user data.
3. Register UUID-to-protocol-identifier associations when requested by pairing. Match rediscovered identities before using secrets, and reject conflicting identities at reused addresses.
4. Implement devices list, alias and default plus the selection precedence in DESIGN.md. Pairing must also resolve an explicit unregistered discovery candidate.
5. Return empty discovery successfully, ambiguous selections with candidate hints, and clear unreachable/identity errors. Document registry location and recovery.

## Acceptance criteria

- [x] Duplicate names never cause arbitrary selection; an invalid explicit ID never falls back.
- [x] DHCP address changes preserve identity; IP reuse by a different TV cannot receive stored credentials.
- [x] Concurrent updates preserve valid registry data and alias uniqueness; interrupted writes retain a usable prior file.

## Validation

Test zero/one/many devices, alias collisions, explicit/default selection, mixed protocol identifiers, IPv4 and explicit IPv6 rejection, corrupt schema, concurrent writers and changed identities with fake scans.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence

- Added a lazily loaded pyatv discovery adapter with normalized tvOS candidates, targeted IPv4 scans, reserved cleanup time and no credential access or registration during discovery.
- Added a versioned nonsecret registry using platformdirs, pinned filelock 3.32.5, bounded cancellable lock acquisition, validated read/modify/write transactions and fsynced temporary files followed by atomic replacement.
- Added UUID registration for future pairing, shared-protocol identity checks, selection precedence, explicit candidate selection, aliases and defaults. Pairing/control remain unavailable until subsequent issues.
- `python -m pytest -q`: **196 passed** locally, including spawned concurrent writers, contested aliases, process termination before replacement, corrupt schemas, DHCP changes, address reuse and mocked scan cancellation.
- Ruff checks/formatting, `uv sync --locked`, `uv pip check`, source/wheel builds, and fresh wheel installation via `python -O tools/check_wheel.py --requirements runtime-requirements.txt` passed.
- On 2026-09-07, macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: live multicast discovery returned two tvOS candidates including the previously validated reference TV; targeted discovery returned that reference TV alone. Both emitted valid success JSON with empty stderr. No pairing, credential persistence or TV control was performed. Device identifiers/address logs remain ignored local artifacts.
- Windows hardware discovery and credential persistence remain issue 001 release gates. Cross-platform CI exercises registry and adapter behavior without a TV.

Usage, platform registry paths, identity semantics and recovery are documented in [docs/registry.md](../docs/registry.md).

### Review follow-up

Bundle the registry guide in wheels and verify its exact installed contents during fresh-wheel checks. Reserve `candidate-` for discovery IDs in alias mutations and registry validation, with recovery guidance for pre-release aliases. Pydantic validation errors already inherited `ValueError` and mapped to `invalid_registry`; split exception branches for clarity and add reason-specific regression assertions. **200 tests pass** locally; Ruff, locked sync, source/wheel build and optimized fresh-wheel checks pass.
