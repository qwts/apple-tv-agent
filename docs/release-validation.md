# Release validation ledger

Candidate package version: `0.1.0a1`. **Development preview, not release-ready.** Issues [001](../issues/001-transport-spike.md) and [010](../issues/010-validation-release.md) retain native hardware gates. The [manual runbook](hardware-validation.md) defines repeatable tests and cleanup.

## Current evidence

| Scope | Evidence | Limit |
| --- | --- | --- |
| macOS / Windows automated matrix | [Run 34141985450](https://github.com/qwts/apple-tv-agent/actions/runs/34141985450), commit `064cd2d`, Python 3.12/3.14: all four jobs passed; 448 tests passed, one opt-in native-vault test skipped per job | Hosted Windows Server is not native Windows 11 hardware validation |
| Clean wheel installation | Each matrix job installs hashed runtime dependencies and the wheel in a fresh environment with spaces in its path; checks both entry points, schema, guides and exported skill | No TV or vault mutation; doctor completion alone does not imply all checks pass |
| Skill | Portable folder and fake-CLI scenarios verified; see [skill validation](skill-validation.md) | Root walkthroughs, not independent model evaluation or actual client installation |
| macOS hardware | Discovery, AirPlay/Companion pairing, Keychain persistence across processes, status and capabilities; see [compatibility](compatibility.md) | Reference Apple TV 4K second generation; tvOS 26.2 previously observed; not a new firmware reading |
| macOS visual control follow-up | Production YouTube launch and left/right/select navigation operated the intended profile/video; [optional LG spike](lg-screen-capture-spike.md) supplied separate visual observation | Screenshot observation is not part of the baseline CLI; no full control matrix or reboot/upgrade validation |
| Windows 11 hardware | Not-tested: discovery, pairing, vault writes/persistence, status, pause/navigation and remaining controls | Blocks the cross-platform release promise |
| Remaining macOS hardware | Production pause/play matrix, Home/menu semantics, focused typing, power/audio-route volume, revoked credentials, locked vault, network interruption, multi-TV ambiguity, upgrade, reboot and production local-removal checks: not-tested as a complete release run | Earlier probe playback and isolated credential tests remain narrower evidence |

## Reproduce automated checks and local artifacts

Use a clean checkout of the commit being assessed and the locked [setup instructions](../skills/apple-tv-control/references/setup.md). Run these from its repository root using that environment's absolute `uv` executable (shown as `uv` below). No global install or TV is required.

```text
uv sync --locked --python 3.14
uv pip check
uv run --locked --no-sync ruff check src tests/contract tests/unit tests/integration tools/verify_pairing.py tools/generate_schema.py tools/check_wheel.py tools/check_skill.py tests/skill
uv run --locked --no-sync ruff format --check src tests/contract tests/unit tests/integration tools/verify_pairing.py tools/generate_schema.py tools/check_wheel.py tools/check_skill.py tests/skill
uv run --locked --no-sync python -m pytest -q
uv run --locked --no-sync python -m build --no-isolation
uv export --locked --no-dev --no-emit-project --output-file runtime-requirements.txt
uv run --locked --no-sync python -O tools/check_wheel.py --requirements runtime-requirements.txt
```

Repeat in a separate clean checkout/environment for Python 3.12. The committed [workflow](../.github/workflows/transport-probe.yml) performs both Python versions on both hosted OSes. Start with an empty `dist` directory; the wheel checker deliberately rejects multiple wheels. Record the commit, exact runtime versions, artifact names and SHA-256 hashes alongside results. Hashes identify bytes, not reproducible-build equivalence.

Before sharing artifacts, inspect both wheel and source-distribution member lists. They must contain only the configured source/package, documentation, skill, schema and build metadata; no `.local`, registry, captures, logs, virtualenvs or secrets. Build configuration allowlists payload paths, but review content too. Store logs locally and report sanitized outcomes. Do not publish packages or tag a stable release as part of this checklist.

The native credential roundtrip is separate and opt-in: in the dedicated test OS account set `APPLE_TV_AGENT_NATIVE_TEST=1` for `python -m pytest -q tests/integration/test_native_credentials.py`, then unset it. This writes a random UUID item, reads it in a new process, deletes it and checks absence. It does not prove production pairing/removal or locked-vault recovery.

## Local issue 010 artifact check (2026-09-07)

On macOS 26.6.2 arm64 / Python 3.14.7, the issue 010 branch passed Ruff checks/formatting, **448 tests with one opt-in skip**, source/wheel build, and the optimized-Python clean wheel checker. Member-list inspection found 36 wheel entries and 38 source-distribution entries, consisting of package/source, documentation, schema and build metadata; no local runtime artifacts were present. These local files were not published:

| Artifact | SHA-256 |
| --- | --- |
| `apple_tv_agent-0.1.0a1-py3-none-any.whl` | `7f5d629a53ef521a6588068557992e1fb7534e97bf880a6c6453c2aaeca123d7` |
| `apple_tv_agent-0.1.0a1.tar.gz` | `6e0b072ce26cd8b24cc1c785513cb7ae54d45e42761e9c4e4bd281fe44776ac1` |

The artifacts were built after the README/registry guide edits and before adding this repository-only evidence section. No hardware mutations or client skill installation were performed for this documentation change.
