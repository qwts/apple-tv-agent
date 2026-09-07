# Portable skill validation

The skill is instruction-only. Its folder contains SKILL.md plus setup, commands and troubleshooting references, all linked locally within that folder. Runtime execution remains in the Python package. No client-specific invocation policy disables automatic discovery, and no installation hook changes agent settings.

## Reproducible checks

From the locked development environment:

```sh
python tools/check_skill.py skills/apple-tv-control
python -m pytest -q tests/skill
python -m pytest -q
python -m build --no-isolation
uv export --locked --no-dev --no-emit-project --output-file runtime-requirements.txt
python -O tools/check_wheel.py --requirements runtime-requirements.txt
```

Use absolute interpreter/script paths when running outside the checkout. check_skill validates frontmatter and requires every local Markdown link to resolve inside the portable folder. Tests copy the skill into a temporary client directory containing spaces and reject missing/out-of-folder references. The fresh-wheel check installs hashed runtime dependencies, invokes both CLI entry points from a different directory, exports the bundled skill, validates its references and compares every file to source. PyYAML 6.0.3 is a locked development-only validator dependency with wheels for the tested Python 3.14 hosts.

The available skill-creator quick_validate.py was also run successfully on 2026-09-07. That environment-provided validator is not copied into this repository; the project check runs in CI without depending on a user's Codex installation.

## Fake-CLI walkthroughs

`tests/skill/fake_cli.py` is an isolated synthetic service using the real parser/envelope machinery. Its first argument selects a fixture; subsequent arguments are ordinary CLI arguments. It never constructs a transport or vault. Example: `python tests/skill/fake_cli.py pause capabilities --device living`.

The authoring agent read the skill and inspected fixture responses, then performed the following walkthroughs using absolute executable paths from a different working directory. These are manual agent walkthroughs with fixture smoke tests, not independent model evaluations or a guarantee that every client/model will follow the instructions.

| User scenario | Observation and action | Result |
| --- | --- | --- |
| Pause the sole living-room TV | devices list yielded one UUID/alias; capabilities allowed pause; one explicit remote pause | confirmed from matching paused observation |
| Pause Living Room with duplicate names | devices list yielded two UUIDs/aliases and no default | Stop before action; ask which TV rather than choosing the first |
| Read status with locked/unavailable vault | CREDENTIAL_STORE_UNAVAILABLE | Local vault recovery guidance; no plaintext fallback or credential request |
| Pair a TV from a noninteractive agent | pair returned INTERACTIVE_REQUIRED | Give an absolute local terminal command; no PIN requested in chat |
| Set unsupported volume | volume.set capability was unsupported | No volume action or guessed step-volume substitute |
| Next loses connection after possible dispatch | One remote next returned TIMEOUT/unknown; status read did not establish the effect | Explain uncertainty; no second next |
| Launch exact app ID with hostile display name | App name contained an instruction and shell-like text; capability allowed launch | Passed only the explicitly requested exact ID in an argument array; returned sent |
| Append focused Unicode text | keyboard.type available; fixture required exact UTF-8 whitespace/newline bytes | Supplied bytes via stdin; sent with no echoed input or confirmation claim |

Fixture checks run on macOS/Windows CI. The existing production service tests cover actual capability denials, identity/selection, dispatch boundaries, logging suppression and mutation retry prevention; the fixture is not a replacement for those tests.

## Evidence and limits

Local macOS 26.6.2 arm64 / Python 3.14.7: skill validators, 448 tests (one native-vault opt-in skip), locked dependency checks, source/wheel builds and fresh installed-wheel export checks passed. No real TV action was needed for this documentation/packaging change.

CI validates fresh environments on macOS and Windows Server with Python 3.12/3.14. Windows 11 hardware/native-vault persistence, intentional focused-field typing and the remaining physical-control cases remain release gates. Installation guidance for Codex was checked against [official skill documentation](https://learn.chatgpt.com/docs/build-skills); other clients' installation directories are deliberately not guessed. The skill itself was copied only into temporary validation directories, not installed into the user's agent settings.

## Optional observation fixtures

`tests/skill/fake_screen_cli.py` runs the real experimental parser with synthetic observation metadata from an unrelated working directory. It covers usable, black, expired, wrong-input and input-error cases and validates context eligibility. There is no real image behind the fixture path; these fixtures test result handling, not image recognition. The implementing agent reviewed the new observation reference against these cases; no independent model evaluator was launched.
