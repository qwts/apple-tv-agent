# Trusted LG pairing and local credentials

The experimental `apple-tv-screen` helper can discover/inspect, pair, list local registrations, verify a saved-key reconnect, and forget local credentials. Optional [HDMI association, one-shot capture and artifact cleanup](lg-capture.md) extend this pairing under [issue 18](https://github.com/qwts/apple-tv-agent/issues/18). No Apple TV pairing or settings are changed by these commands.

## Pair in your local terminal

Use the locked environment's absolute `apple-tv-screen` path; the examples abbreviate it. PowerShell uses `&` before the quoted executable path. Start with [discovery](lg-discovery.md) and select the actual host and UDN from the same candidate. Do not paste discovery output or credentials into shared logs.

```text
apple-tv-screen pair --host TV_IPV4 --udn uuid:DISCOVERED_UUID
apple-tv-screen devices
apple-tv-screen verify --device REGISTERED_LG_UUID
```

`pair` requires a local TTY and refuses before network/vault access otherwise. It rediscovers the selected UDN at the chosen address, inspects its TLS certificate and displays the identity/fingerprint plus the manifest's full permission list on stderr. Type `trust` and Enter locally to accept, or cancel. Trust entry is hidden and limited to 120 seconds. First-use approval is trust on first use, not independent device authentication.

The manifest grants broad rights, including input, power, settings, notifications and update-related access. It is **not screenshot-only permission**. This helper's executable allowlist currently permits registration, system information and foreground-input reads; it exposes no arbitrary SSAP request forwarding. The feasibility probe's smaller unsigned manifest could not capture screenshots. Least-privilege capture is still unproven, so this implementation discloses the known working manifest instead of claiming narrower rights.

After local acceptance, approve the **LG Remote App** prompt on the intended TV within a separate 120-second budget. The application uses a pinned TLS WebSocket on port 3001, rejects redirects, bounds messages to 64 KiB and limits unrelated protocol messages. It reads system information to verify authenticated access and closes the session before saving the key. Pair success requires verified native-vault storage and a paired registry marker. No key or raw SSAP response is printed. The `--timeout` option applies to initial discovery/certificate inspection; human approval phases have their own budgets.

The pinned connection must succeed before `verify` loads a saved key. Verification rediscovers the stored UDN and rejects mismatched certificates. It performs registration and an allowlisted system read, then reports `verified: true`. It sends no TV control. A saved-key rejection fails without automatically continuing into a new pairing. The TV might display a prompt when it rejects a key, but the helper will close rather than accept that prompt. Do not retry authentication by silently re-pairing.

## Registration, address changes and removal

LG records live in `lg-registry.json` beside the baseline Apple TV registry, with a separate lock. Records contain a local UUID, UDN, address, SHA-256 certificate fingerprint and pairing marker; no credential values. Writes use validation, file locking, flush/fsync and atomic replacement. One transaction serializes verification, pairing persistence or deletion; concurrent LG commands may return DEVICE_BUSY after five seconds. The normal-command deadline can expire sooner. Pairing stores an unpaired record before requesting TV registration so failed storage still leaves a UUID for recovery. The marker is not proof that the vault is currently unlocked or a key is present.

Keys use the validated native macOS Keychain or Windows Credential Manager backend, under service `apple-tv-agent-lg`, account `REGISTERED_LG_UUID:ssap`. The existing Apple TV namespace is preserved. Writes verify readback and attempt restoration on failure. No plaintext fallback or credential import/export is provided.

For a changed address, explicitly run `verify --device REGISTERED_LG_UUID --host NEW_IPV4`. The UDN and stored certificate must match before any saved key is loaded. Only successful authenticated verification updates the address. A different device already registered at that address is a conflict. Certificate/identity changes never silently replace existing trust.

```text
apple-tv-screen forget --device REGISTERED_LG_UUID
```

`forget` deletes and verifies absence of the native key before removing the registration. Repeating it is safe, including if the UUID's registration is already absent. It reports `removed_locally: true` and `tv_revocation_verified: false`; local deletion does not revoke TV-side permission. Remove only this test/client pairing on the TV separately when needed. If vault deletion fails, the registration stays available for retry. If the registry write fails after deletion, retrying forget removes the remaining record. Do not delete the registry manually while credentials may still exist.

A changed certificate requires deliberate recovery: confirm that the intended TV changed, forget the old local UUID, remove obsolete TV-side client permission if appropriate, then pair again with explicit local trust approval. Previously paired records refuse `pair`; use `verify`, or deliberate forget/re-pair recovery. Pending records may retry pairing only with the same stored identity/certificate.

Malformed, duplicate-key or unknown-version LG registry files produce CONFIG_ERROR without resetting data. Preserve the file privately before recovery. Never run baseline Apple TV recovery against `lg-registry.json`, or vice versa.

## Output and packaging

The experimental [discovery envelope](lg-discovery.md) is reused: command names additionally include `pair`, `devices`, `verify`, `forget`. Pair returns `{device_id, paired}`, devices returns `{devices: [...]}`, verify returns `{device_id, verified}`, and forget returns the fields above. Pairing prompts are the stderr exception; normal success/errors remain a single JSON stdout object. Fixed error codes use the existing exit mapping, including INTERACTIVE_REQUIRED/AUTH_FAILED/CREDENTIAL_STORE_UNAVAILABLE (3), IDENTITY_MISMATCH (2), TIMEOUT/NETWORK_ERROR/DEVICE_BUSY (5) and CONFIG_ERROR (6).

The public registration manifest and its MIT license are bundled under `apple_tv_agent/observation/`. Source: [bscpylgtv manifest at f631c390](https://github.com/chros73/bscpylgtv/blob/f631c3908a21d12725329277a0bd4b50d0da6de7/bscpylgtv/manifest.py), with [upstream license](https://github.com/chros73/bscpylgtv/blob/f631c3908a21d12725329277a0bd4b50d0da6de7/LICENSE.txt). Its public signature is manifest data, not a TV client key. The manifest is preserved unchanged for reproducibility.

## Validation boundary

Offline tests cover explicit trust, peer errors, key validation, permission failures, credential namespace separation, identity/pin-before-key ordering, pending records, cancellation, deletion failure and invalid registry preservation. They do not establish native Windows pairing, actual TV permissions or a usable screenshot. Hardware pairing requires local trust and TV approval; the earlier probe's credentials are never imported automatically.

### Reference Mac validation (2026-09-07)

On macOS 26.6.2 arm64 / Python 3.14.7, local trust acceptance and LG approval completed against the reference TV previously identified as OLED65C2PUA (firmware 33.31.68 from earlier evidence; not reread here). The pinned session registered and read system information, and verified Keychain storage succeeded. A separate production CLI process then verified saved-key reconnect with exit 0 and empty stderr. No controls or screenshots were requested. An initial temporary launcher scan found no candidate; a later targeted/multicast check found the TV before the successful pairing attempt. No firewall cause was inferred.

The opt-in isolated LG vault test also wrote a random test item, read it in a fresh process, deleted it and verified absence. The reference pairing is retained for subsequent capture work; production forget was tested with synthetic storage, not by deleting that pairing. Native Windows pairing/reconnect/removal remain untested.
