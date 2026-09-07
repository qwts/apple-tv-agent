# Pairing and native credentials

Run `apple-tv-agent discover` and then `apple-tv-agent pair --device CANDIDATE_ID` in a local interactive terminal. Existing registered UUIDs, aliases and the saved default follow the normal selection rules. A new TV requires an explicit current candidate ID. Discovery and pairing may require firewall approval; rerun after approving. The CLI never changes firewall rules.

The TV displays each PIN. Enter it only into the local terminal's hidden prompt. Do not paste PINs into agent chat, pass them as arguments, or store them in files/environment variables. There is no echoing fallback. Terminal input is polled without a blocked input thread, and macOS terminal settings are restored on timeout/cancellation. Ctrl-C cancels the current operation. Do not type until the hidden PIN prompt appears.

The implementation pairs advertised AirPlay, Companion and MRP services when their requirement is mandatory or optional. These provide the project's control path; RAOP/DMAP streaming/legacy pairing is outside this workflow. A service advertised as not needing pairing is reported `not_needed`. Disabled/unsupported services are not paired. Each attempt owns a handler from begin through PIN entry and finish, with a 120-second deadline and bounded cleanup. An authentication failure permits at most three manually entered attempts per protocol; timeouts, canceled input and network/vault failures stop the operation. `--timeout` bounds discovery; human-input attempts use their separate deadline.

Before saving a new credential, the adapter authenticates it in a fresh session. AirPlay uses explicit Pair-Verify because pyatv's AirPlay connect path alone can be a no-op; Companion/MRP authenticate through their connect handshakes. These APIs are isolated behind the pinned pyatv 0.18.0 adapter. No playback or navigation command is used for verification.

## Storage and partial results

Only the exact native keyring backend is accepted: macOS Keychain or Windows Credential Manager. Plaintext, null, chained and unknown backends fail closed. Unlock the native vault and allow the Python application access when prompted. OS vault access can require a native dialog; synchronous native calls are not forcibly terminated in a background thread, avoiding writes continuing after a reported cancellation.

Credentials use service `apple-tv-agent` and account `DEVICE_UUID:protocol`; values are never written to the registry. In-memory pyatv settings are hydrated from the vault only after rediscovered protocol identity matches the registered device. Protocol-library logging is disabled during credential-bearing operations because upstream debug messages can contain PINs and credentials. Errors contain fixed classifications and nonsecret progress, never raw exception strings.

Pairing returns success only after verification, native-vault write/readback and registry bookkeeping succeed. Failed re-pairing leaves existing local credentials intact; failed vault writes attempt to restore the previous value. If restoration cannot be verified, the error says so. Local preservation does not promise that the TV has kept an older pairing valid. When a later protocol fails, the error's `protocols` map records earlier `paired` protocols and the failed protocol; `device_id` identifies the registered device for recovery. A partially registered device can remain for an explicit retry or local removal. No automatic re-pairing occurs on reconnect authentication failure.

Per-device native file locks serialize pairing and credential deletion. Candidate locks also serialize simultaneous initial pairing of the same discovery candidate. Other operations wait at most five seconds for a busy device. Registry aliases/default updates use their separate transactional lock.

## Reconnect validation

The production status/control commands arrive in the next issues. From a checkout, verify persisted credentials in a separate process without pairing or device control:

```sh
python tools/verify_pairing.py --device DEVICE_UUID
```

The tool performs current discovery and identity checks before vault reads, authenticates the saved protocols and closes connections. It prints only success/protocol labels or a generic verification failure. It never outputs credentials or requests PINs. Use the virtual environment's Python interpreter. Windows uses `.venv\Scripts\python.exe`; macOS uses `.venv/bin/python`.

An opt-in isolated native-vault test generates a temporary random credential, validates it in a new process and removes it. macOS: `APPLE_TV_AGENT_NATIVE_TEST=1 .venv/bin/python -m pytest tests/integration/test_native_credentials.py -q`. PowerShell: set `$env:APPLE_TV_AGENT_NATIVE_TEST='1'`, run `& .\.venv\Scripts\python.exe -m pytest tests/integration/test_native_credentials.py -q`, then `Remove-Item Env:APPLE_TV_AGENT_NATIVE_TEST`. The normal suite skips this native operation.

## Local removal

`apple-tv-agent devices forget --device UUID_OR_ALIAS` removes all protocol credentials under that UUID, then removes the registry record and clears a matching default. This removes local access; it does not guarantee revocation of pairing on the TV. Other TVs are untouched.

A vault deletion failure retains the registry record/default and reports removed/failed protocol labels. Unlock the vault and retry with the returned UUID. Repeating a successful deletion with the same explicit UUID is idempotent, including after the registry record is gone. An alias no longer resolves after successful deletion. If credentials were removed but the registry update failed, timed out or was canceled, the error retains `device_id`, `local_credentials_removed=true` and `registry_removed=false` for the same UUID retry. Deadline expiry returns `TIMEOUT`; user cancellation during the registry update returns `CONFIG_ERROR` with `reason=canceled`. Keep the registry intact until coordinated deletion succeeds.

Windows native-vault and Windows 11 TV hardware validation remain release gates; passing simulated tests or Windows CI is not hardware evidence.
