# 002: Create the Python package and JSON CLI contract

GitHub: https://github.com/qwts/apple-tv-agent/issues/2
Status: open
Priority: P0
Depends on: [001](001-transport-spike.md)

## Outcome

Establish an installable local package and stable machine-readable interface for the agent.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Create pyproject.toml and a src-layout package with console and module entry points. Pin the proven transport and define reproducible development dependencies using a documented lock workflow.
2. Implement typed envelope, command payloads, normalized capability/state models and error classes from DESIGN.md. Add a versioned JSON schema and exact error-to-exit mapping in docs/cli-contract.md.
3. Build the full parser with allowlisted subcommands, device selection options, deadline validation, finite volume bounds and stdin text size limits. Commands awaiting implementation must return explicit unavailable errors, never fake success.
4. Define adapter, registry and credential-store interfaces and a deterministic fake adapter for subsequent issues. Keep pyatv imports inside the adapter.
5. Ensure argument/parser failures also produce JSON, help/version remain readable, logs use stderr, and both entry points behave identically.

## Acceptance criteria

- [ ] Fresh local wheel installation exposes both entry points on macOS and Windows.
- [ ] Success, parser failure and unexpected exception outputs conform to the schema and exit mapping.
- [ ] Invalid inputs cause no discovery, credential access or device mutation.

## Validation

Use contract tests for valid/invalid commands, malformed numeric values, Unicode JSON, stdout cleanliness, and equivalence of entry points. Build and install a wheel in an isolated environment.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
