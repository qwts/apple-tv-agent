# 003: Implement discovery, durable identity and device selection

Status: open
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

- [ ] Duplicate names never cause arbitrary selection; an invalid explicit ID never falls back.
- [ ] DHCP address changes preserve identity; IP reuse by a different TV cannot receive stored credentials.
- [ ] Concurrent updates preserve valid registry data and alias uniqueness; interrupted writes retain a usable prior file.

## Validation

Test zero/one/many devices, alias collisions, explicit/default selection, mixed protocol identifiers, IPv4/IPv6, corrupt schema, concurrent writers and changed identities with fake scans.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
