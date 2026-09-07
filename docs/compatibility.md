# Transport feasibility evidence

Issue: [001](../issues/001-transport-spike.md). Status: **in progress**; hardware and Windows gates remain open. Observed 2026-09-07 UTC (2026-09-06 local).

## Dependency decision

Candidate transport pin: `pyatv==0.18.0` (MIT, package metadata requires Python >=3.9). Candidate vault dependency: `keyring==25.7.0` (MIT, requires Python >=3.9). Probe tests use `pytest==9.1.1`. These are direct pins in [requirements-spike.txt](../tools/requirements-spike.txt), not a transitive production lock.

The design's Python 3.12 baseline remains a candidate. The available modern interpreter on this Mac is Python 3.14.7; the probe was exercised with it. The probe itself requires Python >=3.11 for `asyncio.timeout`. Python 3.12 installation and fake-backed behavior now pass on both hosted OS runners (see CI evidence below); Windows 11 hardware behavior remains unverified. Do not infer supported platforms from package classifiers alone.

The install resolved binary macOS arm64/universal wheels for the compiled dependencies (including aiohttp, cryptography, miniaudio, protobuf, pydantic-core and zeroconf); no local compilation was needed. `pip check` found no broken requirements. Reproduce and lock the validated cross-platform set in issue 002.

Primary references: [pyatv release metadata](https://pypi.org/project/pyatv/0.18.0/), [tagged source](https://github.com/postlund/pyatv/tree/v0.18.0), [keyring release metadata](https://pypi.org/project/keyring/25.7.0/). API findings below were checked against the installed 0.18.0 wheel, not only rolling online docs.

## Local hardware observations

| Check | macOS 26.6.2, arm64, Python 3.14.7 | Native Windows 11 x64 |
| --- | --- | --- |
| Fresh venv dependency installation | Pass | Not tested on Windows 11; see hosted CI below |
| Dependency consistency (`pip check`) | Pass | Not tested |
| Probe unit tests | 17 passed | Not tested |
| Native backend selected | `keyring.backends.macOS.Keyring` | Not tested; expected `keyring.backends.Windows.WinVaultKeyring` |
| Disposable vault write/read/delete | Pass outside execution sandbox; deletion verified | Not tested |
| Multicast discovery | Initial five-second scan: zero candidates; subsequent ten-second scan: nine AirPlay devices, including two pairable candidates | Not tested |
| Direct IPv4 discovery | Pass; selected Apple TV 4K (second generation), tvOS 26.2 | Not tested |
| PIN pairing and connection | Pass; AirPlay + Companion, ephemeral credentials | Not tested |
| Status, pause, keyboard focus | Status/focus read passed; pause sent once and user observed TV paused afterwards | Not tested |
| Locked vault behavior | Not tested; do not lock the user's vault automatically | Not tested |

The sandbox initially denied LAN access (`PermissionError`) and Keychain operations (`KeyringError`). The same opted-in commands succeeded outside the sandbox. These are execution-context observations, not proof of locked-vault recovery or firewall behavior. The user reported a Little Snitch approval prompt. A subsequent ten-second scan found nine devices, including two candidates advertising mandatory AirPlay and Companion pairing. This is consistent with traffic being permitted after approval; the scan itself cannot prove the firewall was the cause of the earlier empty result. The subsequent interactive AirPlay/Companion session succeeded, read status/focus and sent pause once. The user reported the TV paused afterwards.

## API mapping for implementation

| Project function | Verified 0.18.0 API / feature | Notes |
| --- | --- | --- |
| Scan | `await pyatv.scan(loop, timeout=5, hosts=None, storage=storage)` | `hosts` is a list of IPv4 strings. Library converts each with `IPv4Address`; IPv6 is rejected. |
| Identity | `config.identifier`, `config.all_identifiers`, service `identifier` | Main identifier prioritizes protocols; retain per-protocol identities because the chosen main identifier may change with services. |
| Pairing requirements | `service.pairing`, `service.enabled` | Requirements describe each advertised service; do not pair every known protocol blindly. |
| Pair | `await pyatv.pair(config, protocol, loop, storage=storage)` | Handler exposes `device_provides_pin`, `begin`, `pin`, `finish`, `has_paired`, `close`. |
| Ephemeral storage | `MemoryStorage()`; `await load()` | No filename, no credentials on disk. Shared instance goes to scan/pair/connect. |
| Connect | `await pyatv.connect(config, loop, storage=storage)` | Let pyatv build its protocol facade. |
| Disconnect | `connection.close()` | Synchronous method returns a set of asynchronous tasks; await these tasks. |
| Capabilities | `features.all_features(include_unsupported=True)` and `get_feature(FeatureName)` | States are available, unavailable, unsupported, unknown. Do not serialize raw feature options. |
| Playback status | `await metadata.playing()` | Properties include `device_state`; field availability still needs checks in the product. |
| Navigation/playback | `remote_control.up/down/left/right/select/menu/home/play/pause/stop/next/previous()` | Corresponding `FeatureName` values use PascalCase. `Home` and `TopMenu` are distinct; physical behavior awaits hardware validation. |
| Power | `power.turn_on/turn_off(await_new_state=False)` | `TurnOn`, `TurnOff`, `PowerState`; observation requires separate readback. |
| Volume | `audio.volume_up/volume_down/set_volume(level)` | `VolumeUp`, `VolumeDown`, `SetVolume`; route support needs hardware verification. |
| Apps | `apps.app_list()`, `apps.launch_app(bundle_id_or_url)` | `AppList`, `LaunchApp`; wrapper must restrict launch to installed IDs despite the broader upstream API. |
| Keyboard | `keyboard.text_focus_state`, `keyboard.text_append(text)` | `TextFocusState`, `TextAppend`; require `KeyboardFocusState.Focused`. |

`text_append` implements “type” without replacing existing text. Upstream `text_set` replaces the field and should not be substituted silently. Neither requires reading the current text into agent output. The probe only reads focus and never reads or sends keyboard text.

The public design now explicitly scopes discovery to IPv4. The original IPv6 promise was incompatible with the selected transport. Hardware tests must still establish protocol pairing prerequisites and the behavior of Home, power, volume and focused typing.

## Probe usage

Run from this worktree/repository root. No global package installation or shell activation is required. Interpreter paths below are examples; select an installed supported Python.

macOS:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-spike.txt
.venv/bin/python tools/transport_probe.py environment
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python tools/transport_probe.py vault-roundtrip
.venv/bin/python tools/transport_probe.py discover --timeout 5
```

Windows PowerShell (instructions prepared; not yet validated on Windows):

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r tools/requirements-spike.txt
& .\.venv\Scripts\python.exe tools/transport_probe.py environment
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe tools/transport_probe.py vault-roundtrip
& .\.venv\Scripts\python.exe tools/transport_probe.py discover --timeout 5
```

`environment` selects a backend but does not read/write a secret or access the LAN. `vault-roundtrip` creates only a random test item under `apple-tv-agent.transport-probe`, checks it and deletes it. A failure must be investigated rather than taken as proof of cleanup; no existing credentials are read. The probe intentionally avoids printing underlying exception messages.

If multicast finds nothing, use the TV's actual IPv4 address (the documentation address below is deliberately non-routable):

```sh
.venv/bin/python tools/transport_probe.py discover --host 192.0.2.10 --timeout 5
```

Run a session **in a local interactive terminal** with the identifier from discovery, selecting advertised AirPlay and/or Companion services as appropriate:

```sh
.venv/bin/python tools/transport_probe.py session --identifier DEVICE_ID --protocol AirPlay --protocol Companion
```

Enter the PIN only at the hidden local prompt. Each protocol gets one attempt with a 120-second pairing deadline. Cancellation restores terminal settings. No TV credentials are persisted; rerunning requires pairing again. Existing pairing entries may remain on the TV after this ephemeral client exits; remove test entries on the TV if desired.

The session reads capabilities, playback state and available keyboard focus. Add `--pause` only when deliberately testing pause on that TV. It sends at most one pause; it never claims the effect was confirmed. Alternatively, use `--play` to send one capability-gated Play and check playback-state readback. The two flags are mutually exclusive. Unlike the future production CLI, this probe uses per-phase deadlines plus separate cleanup deadlines, argparse's normal human-readable usage errors, and no registry or cross-process device lock. Run one session at a time. It is a feasibility tool, not an installable agent skill.

Do not commit raw discovery output, PINs, credentials, device identifiers, network addresses or media text as evidence. Record model/tvOS and sanitized outcomes manually.

For a requested Play/Pause, a failed probe reports `outcome: not_sent` when it
fails before playback dispatch (including discovery, pairing and capability
checks). Once dispatch starts, a subsequent dispatch, readback or cleanup failure
reports `outcome: unknown`. This field describes the requested playback action,
not side effects of pairing itself. Errors without a requested playback action
keep `outcome: null`.

## Remaining gates and next steps

1. Keep the remaining validation work on the issue-specific branch and record results in the PR before declaring issue 001 complete.
2. Record further control semantics on the selected Apple TV 4K (second generation), tvOS 26.2. Targeted discovery, AirPlay/Companion pairing and status passed; pause was dispatched and the user observed the TV paused afterwards. Record model, tvOS, topology, protocol requirements and outcomes.
3. Run installation, tests, native-vault checks and baseline hardware controls from Windows 11 x64. Repeat with Python 3.12 if retaining it as the production baseline.
4. Validate locked-vault recovery and Home semantics without guessing from API names. Only then mark issue 001 complete and freeze the production contract in issue 002.

### Resume playback follow-up

The first fresh pairing attempt for Play failed; the user reported a possible mistyped PIN. After a user-requested retry in local Terminal, the user confirmed playback resumed. The probe sent at most one Play per successful session and did not retry a dispatched mutation.

Probe result: Play `sent`; playback readback `paused`.

## Automated cross-platform evidence

[GitHub Actions run 34085123063](https://github.com/qwts/apple-tv-agent/actions/runs/34085123063), commit `670d975`, completed successfully on 2026-09-07 UTC. All four jobs installed the pinned direct dependencies, passed `pip check`, selected the expected native keyring backend, and passed all 17 probe tests.

| Runner OS | Architecture | Python | Result |
| --- | --- | --- | --- |
| macOS 26.6.2 | arm64 | 3.12.10 | Pass |
| macOS 26.6.2 | arm64 | 3.14.7 | Pass |
| Windows Server 2025 | AMD64 | 3.12.10 | Pass |
| Windows Server 2025 | AMD64 | 3.14.7 | Pass |

Windows selected `keyring.backends.Windows.WinVaultKeyring`; macOS selected `keyring.backends.macOS.Keyring`. CI does not perform native-vault writes or LAN/hardware operations. Windows Server installation and fake-backed test success do not establish Windows 11 interactive pairing or credential persistence.

## Package foundation validation (issue 002)

[Run 34088665314](https://github.com/qwts/apple-tv-agent/actions/runs/34088665314), commit `fd0ea01`, passed on macOS and Windows runners with Python 3.12 and 3.14. Each job synchronized the universal dependency lock, checked native backend selection, passed Ruff and all **143 tests**, built a source distribution and wheel, then installed the wheel with hashed runtime dependencies in a fresh temporary virtual environment. Both CLI entry points and the bundled schema passed checks from a path containing spaces outside the checkout.

These package checks require no TV or persisted credentials. They establish installation and contract behavior; the Windows 11 hardware and native-vault persistence gates in issue 001 remain open.

## Persisted pairing validation (issue 004)

On 2026-09-07, macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: the production CLI paired the reference Apple TV 4K (second generation, previously observed tvOS 26.2) over AirPlay and Companion using hidden local-terminal PIN entry. Verified credentials were saved to Keychain. A separate Python process read them only after rediscovered identity matched and authenticated both protocols; this read-only reconnect was repeated after connection cleanup changes. No playback/navigation actions were sent.

The new opt-in native-vault test passed an isolated write, fresh-process read and verified deletion. The normal suite covers failures, rollback and cancellation with synthetic credentials; native Windows vault mutation and Windows 11 pairing/restart remain untested release gates. MRP pairing is implemented against the pinned API but has no hardware evidence in this run.

## Production status/capabilities validation (issue 005)

On 2026-09-07, macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0: separate production CLI status and capability invocations connected to the registered reference TV using Keychain credentials and returned success JSON with empty stderr. Status observed playback `playing`. No re-pairing, playback or navigation action was sent. Windows 11 TV status/capability validation remains untested; simulated cross-platform tests are not a substitute for that hardware evidence.

### Core-control implementation check (2026-09-07)

On the same macOS 26.6.2 arm64 host, Python 3.14.7 and pyatv 0.18.0 reconnected with saved credentials. Production status reported off/idle; capabilities marked playback unavailable. `remote play` returned FEATURE_UNAVAILABLE with not_sent, retryable false and empty stderr. No control was dispatched. Successful production playback/power/volume effects and physical home/menu behavior remain untested, as does Windows 11 hardware. Automated control/session validation passes 338 tests with one native-vault opt-in skip; see [control semantics](controls.md).

### App listing and launch (2026-09-07)

The reference macOS 26.6.2 arm64 / Python 3.14.7 / pyatv 0.18.0 host retrieved 28 launchable apps using saved credentials. A single launch of the exact installed Netflix bundle ID completed with sent and empty stderr. This confirms transport completion only; the visible foreground app was not independently confirmed. Intentional focused-field keyboard typing and Windows 11 hardware remain untested. Automated suite: 391 passed, one native-vault opt-in skip.
