# 002: Create the Python package and JSON CLI contract

GitHub: https://github.com/qwts/apple-tv-agent/issues/2
Status: in review
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

- [x] Fresh local wheel installation exposes both entry points on macOS and Windows.
- [x] Success, parser failure and unexpected exception outputs conform to the schema and exit mapping.
- [x] Invalid inputs cause no discovery, credential access or device mutation.

## Validation

Use contract tests for valid/invalid commands, malformed numeric values, Unicode JSON, stdout cleanliness, and equivalence of entry points. Build and install a wheel in an isolated environment.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.

### Implementation evidence

- Added the Python package, both entry points, typed payloads for all 29 commands, JSON schema, error catalog, validated requests, dependency protocols and an explicit unavailable default service.
- Added a deterministic test-only fake adapter; invalid arguments and stdin fail before service construction.
- `uv.lock` records cross-platform runtime/development resolution; wheel build uses locked build dependencies and includes the response schema.
- Fresh local macOS wheel installation passed from a temporary directory containing spaces. CI now repeats fresh wheel installation and both-entry-point checks on macOS and Windows with Python 3.12/3.14.
- Issue 001 remains open for Windows 11 hardware and native-vault persistence. This issue implements the development contract without waiving those release gates.

Local validation: **143 tests passed** (contract and existing transport suites); Ruff checks/formatting, lock consistency, dependency checks, source/wheel build, and fresh wheel entry-point smoke tests passed on macOS arm64 / Python 3.14.7. All four cross-platform CI jobs passed in [run 34088665314](https://github.com/qwts/apple-tv-agent/actions/runs/34088665314): macOS and Windows, each on Python 3.12 and 3.14, including all 143 tests and clean wheel installation. Implementation PR: [#12](https://github.com/qwts/apple-tv-agent/pull/12).

### Review follow-up

Global successes now require a null device ID; CLI and response identifiers share character constraints reflected in JSON Schema; pairing respects supplied stdin; wheel checks use explicit exceptions so optimization cannot disable them. Regression coverage passes with **169 tests**, Ruff and a fresh wheel installation checked using `python -O`.
