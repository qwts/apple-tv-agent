# Navigation, playback, power and volume

After local pairing, use `apple-tv-agent remote play --device UUID_OR_ALIAS`, `apple-tv-agent power on --device UUID_OR_ALIAS`, or `apple-tv-agent volume set --level 25 --device UUID_OR_ALIAS`. Omit the selector for the saved default or sole registered TV. See [setup](cli-contract.md), [pairing](pairing.md), and [session ownership and deadlines](sessions.md).

## Exact command mappings

Each action requires its own pyatv capability to be `available` immediately before dispatch. Unsupported features return `UNSUPPORTED_FEATURE`; unavailable or unknown features return `FEATURE_UNAVAILABLE`. No alternate button, toggle, protocol command, or automatic re-pairing is substituted.

| CLI action | Pinned pyatv API |
| --- | --- |
| `remote up/down/left/right/select` | Matching `remote_control` method |
| `remote menu` | `remote_control.menu()` (Menu/back button) |
| `remote home` | `remote_control.home()` (Home/TV button) |
| `remote play/pause/stop/next/previous` | Matching explicit `remote_control` method |
| `power on/off` | `power.turn_on/turn_off(await_new_state=False)` |
| `volume up/down` | `audio.volume_up/volume_down()` |
| `volume set --level LEVEL` | `audio.set_volume(level=LEVEL)` |

Home/TV is distinct from Top Menu. Its visible destination depends on the TV button configuration and current app; it does not promise the home screen. Menu/back is a single press, not a repeated escape sequence. These mappings follow the pinned library API; physical home/menu behavior remains a hardware validation gate.

Absolute volume accepts finite numbers from 0 through 100, including endpoints. CLI validation rejects invalid levels before constructing a service or connecting. An available step-volume feature does not imply support for absolute volume. Power may affect a connected display or receiver through HDMI-CEC; volume affects the active supported audio route. Neither confirms the physical display or speaker response independently.

## Dispatch and outcomes

The selected device's lock covers connection, capability checks, one dispatch, readback and cleanup. Mutations never retry automatically, even after a connection failure before dispatch. The command's original deadline includes cleanup.

- `confirmed`: a subsequent observation matches explicit play/pause/stop or power state; absolute volume matches within 0.01 percentage point; step volume moved in the requested direction from an available baseline observation.
- `sent`: dispatch returned successfully, but readback is missing or mismatched. Navigation, next and previous always report sent because this implementation cannot reliably observe their effect.
- Errors include `details.outcome=not_sent` before the dispatch boundary or `unknown` after possible dispatch. This includes transport loss, deadline expiry, cancellation and cleanup failure. All mutation errors have `retryable=false`.

Playback, power and volume take one bounded status read after dispatch. Volume steps also read a baseline when volume observation is available. A delayed effect can therefore remain sent; reaching a volume boundary with no change also remains sent. Confirmation establishes matching observed state, not causation: the desired state may already have held. Readback transport failure returns an unknown-outcome error, never fabricated confirmation. Inspect status before deciding whether to issue another action after uncertainty.

## Validation limits

Automated tests exercise every mapping, capability denial, invalid and boundary levels, matching/mismatched observations, and failures before/after dispatch with no retry. On the reference macOS host, saved credentials retrieved real status/capabilities and an unavailable play action returned `FEATURE_UNAVAILABLE`, `not_sent`, and no stderr while the TV reported off/idle. Successful production playback/power/volume effects, physical home/menu semantics, and Windows 11 hardware remain unverified. Earlier transport-probe pause/play evidence does not replace those release checks.
