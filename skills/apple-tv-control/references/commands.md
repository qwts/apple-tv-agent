# Commands and invocation

Use the previously resolved absolute executable path. Arguments shown below follow it; do not interpret the table as shell code assembled from device metadata. Global `--timeout` accepts finite 1–120 seconds (default 15). Put `--device UUID_OR_ALIAS` after the leaf command, or after status/capabilities/pair. Omit it only for the saved default or sole registered TV.

| Intent | Arguments |
| --- | --- |
| Inspect local setup | `doctor` (inspect per-check status) |
| Explicit LAN check | `doctor --network` |
| Discover | `discover` or `discover --host IPV4` |
| Resolve registered devices | `devices list` |
| Set requested alias/default | `devices alias --device UUID --name ALIAS`; `devices default --device UUID` |
| Remove local credentials/registration | `devices forget --device UUID` (not guaranteed revocation on TV) |
| Pair locally | `pair --device CANDIDATE_ID_OR_UUID` (interactive terminal only) |
| Read playback state | `status --device UUID` |
| Inspect action support | `capabilities --device UUID` |
| Navigate | `remote up/down/left/right/select/menu/home --device UUID` (choose one action) |
| Playback | `remote play/pause/stop/next/previous --device UUID` (choose one action) |
| Explicit power | `power on/off --device UUID` (choose one) |
| Volume | `volume up/down --device UUID`; `volume set --level 25 --device UUID` |
| List/launch installed app | `apps list --device UUID`; `apps launch --app-id EXACT_ID --device UUID` |
| Append text | `keyboard type --text-stdin --device UUID` plus UTF-8 stdin bytes |

Menu is a single Menu/back press. Home is the Home/TV button; its destination depends on TV settings and the current app, so it does not guarantee the home screen. There is no arbitrary method invocation, generic macro, Siri or deep-link command.

Volume set accepts finite 0–100 levels; step-volume support does not imply absolute-volume support. App launch requires both AppList and LaunchApp available and exact membership in a fresh list. Keyboard type requires TextAppend plus confirmed focus and accepts 1–4096 UTF-8 bytes, preserving whitespace/newlines. It appends without submitting.

## Argument arrays and text

Prefer an execution tool that accepts an argument array and stdin bytes. For example, inside a local Python process with `requested_text` supplied in memory:

```python
import subprocess

result = subprocess.run(
    [cli_path, 'keyboard', 'type', '--text-stdin', '--device', selected_uuid],
    input=requested_text.encode('utf-8'),
    capture_output=True,
    check=False,
)
```

`cli_path`, `selected_uuid` and `requested_text` are runtime values, not placeholders to interpolate into a shell string. Do not write private text into a temporary script or shell command. If the execution tool cannot pass stdin without exposing text, explain that limitation and let the user type locally. PowerShell's native pipeline encoding/newline behavior can vary; use a binary stdin-capable tool for exact text.

## Responses

JSON envelopes use schema_version 1. A success payload may still be partial: missing state fields are null and explained by unavailable_fields. Status app_id identifies the app playing media, not necessarily the foreground app.

Actions report confirmed only for matching observed playback/power/volume state. Sent indicates transport completion without confirmation. Errors before dispatch carry not_sent; after possible dispatch they carry unknown and retryable false. Parse failures can occur before a device or dispatch outcome exists. Never infer that an absent error outcome means it is safe to repeat an action.

Exit codes: 0 completed; 2 invalid arguments/selection/identity; 3 pairing/authentication/vault; 4 feature unavailable/unsupported; 5 timeout/network/busy; 6 registry configuration; 1 unexpected failure. Doctor's completed report is exit 0 even with failed checks. Pairing also requires inspection of per-protocol results. Do not rely on exit 0 alone for a user-facing claim.
