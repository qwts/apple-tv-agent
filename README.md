# Apple TV Agent

Control a local Apple TV from an agent running on your Mac or Windows computer. The Python CLI discovers and pairs devices, reads status, sends remote/playback/power/volume commands, launches installed apps, and appends text to focused inputs. The portable [apple-tv-control skill](skills/apple-tv-control/SKILL.md) teaches an agent how to use those commands and interpret their results.

**Development preview:** macOS hardware has been exercised; macOS/Windows CI checks installation and simulated behavior on Python 3.12/3.14. Windows 11 TV/native-vault hardware validation remains open. See [compatibility evidence](docs/compatibility.md). There is no published package-index release yet.

## Install

Clone a reviewed revision of this repository, then follow the [macOS or PowerShell setup instructions](skills/apple-tv-control/references/setup.md). They install the locked environment and use absolute executable paths, so you do not need shell activation or a particular working directory.

Install the CLI and skill separately:

1. Install the Python package from the checkout using its committed uv.lock.
2. Copy `skills/apple-tv-control` with all its references into your client's skill directory. For current Codex, the documented user location is `~/.agents/skills`; [copy instructions](skills/apple-tv-control/references/setup.md) refuse to overwrite an existing skill. No client settings are changed automatically.
3. Give your agent the absolute path to the installed `apple-tv-agent` executable. The agent must be able to execute locally on the TV's LAN; a cloud-only session cannot reach it automatically.

[Official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)

## Pair and use

Using your installed executable (shown as `apple-tv-agent` below):

```text
apple-tv-agent doctor
apple-tv-agent discover
apple-tv-agent pair --device CANDIDATE_ID
apple-tv-agent devices list
apple-tv-agent capabilities --device REGISTERED_UUID
apple-tv-agent status --device REGISTERED_UUID
apple-tv-agent remote pause --device REGISTERED_UUID
apple-tv-agent apps list --device REGISTERED_UUID
apple-tv-agent apps launch --device REGISTERED_UUID --app-id EXACT_INSTALLED_APP_ID
```

Pairing runs in your own interactive terminal with hidden PIN entry. Verified credentials stay in macOS Keychain or Windows Credential Manager; each computer pairs independently. No Apple ID password or developer account is required. See [pairing and recovery](docs/pairing.md).

Once paired, ask the agent “pause the living room Apple TV,” “open YouTube,” or “tell me what is playing.” Explicit UUID/alias selection takes precedence over a saved default or the sole registered TV. Ambiguous devices require a choice before control.

Ordinary commands emit JSON. A control can be `confirmed` by matching observed state or merely `sent`; a connection failure after possible dispatch reports `unknown`. Actions are never retried automatically. Missing metadata remains null. Read [command semantics](docs/controls.md), [apps and keyboard](docs/apps-keyboard.md), and [diagnostics](docs/troubleshooting.md) for limits and recovery.

## Limits and development

Capabilities depend on the TV, active app and audio/display setup. The baseline CLI does not expose screenshots, screen reading, Siri, purchases, arbitrary deep links or internet remote access. An optional LG provider has [HDMI screenshot feasibility evidence](docs/lg-screen-capture-spike.md) and a [follow-up implementation plan](issues/011-lg-screen-observation.md); it is not yet a packaged capability.

- [DESIGN.md](DESIGN.md): architecture, contracts and release boundaries.
- [Issue backlog](issues/README.md): implementation plans and validation evidence.
- [CLI contract and development checks](docs/cli-contract.md): locked setup, tests and package builds.
- [Release validation](docs/release-validation.md): automated evidence, local artifact reproduction and outstanding hardware gates.
- [Hardware runbook](docs/hardware-validation.md): opt-in Mac/Windows tests with isolated accounts and cleanup.
- [Skill validation](docs/skill-validation.md): portable packaging checks and fake-CLI walkthroughs.

The project uses pinned [pyatv](https://pyatv.dev/documentation/) APIs behind a stable CLI adapter and is independent of Apple and pyatv. Build artifacts remain local until publication is explicitly requested.
