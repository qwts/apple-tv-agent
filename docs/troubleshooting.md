# Diagnostics and recovery

Run `apple-tv-agent doctor` in the same environment the agent uses. It reports package/Python/platform information, dependency versions against the exact runtime pins and importability, virtual-environment context, native credential backend selection and registry readability. It does not print executable paths, device names, addresses, identifiers, credentials, input text, environment variables or raw exceptions.

A completed report exits 0 with `ok=true`, even when individual checks are fail or not_tested. Inspect `data.checks`; success means the report completed, not that the TV is controllable. Parser errors, overall deadline expiry and unexpected report failures retain the usual error envelopes and exit codes. If a foundational import needed to start the CLI is broken, doctor cannot run: recover the environment first using the locked setup in [cli-contract.md](cli-contract.md).

The native-backend check does not read or write a credential. A pass establishes backend selection only; a locked vault and saved credentials remain untested. Registry reads use the existing lock and may create local lock directories/files; doctor never resets or repairs the registry. A pairing marker is not proof that a credential exists or is accepted by the TV.

## Network observations

`apple-tv-agent doctor --network --timeout 15` adds bounded multicast discovery. It sends no pairing or TV control commands and does not alter firewall/network settings. Results contain candidate counts, not discovered device metadata. A candidate establishes a discovery response, not successful authentication or control. An empty scan cannot distinguish a sleeping/disconnected TV, multicast filtering, VPN routing, guest isolation or a firewall. A timeout or transport failure is reported as an observation with next steps.

Try `apple-tv-agent discover --host IPV4` with the TV's current LAN address if multicast returns no results. This is targeted discovery, not an identity bypass: subsequent connection still checks the registered protocol identity. Confirm the computer and TV are connected to the intended LAN; guest networks, client isolation, separate VLANs and active VPN routes may prevent discovery or direct connectivity. Recheck after reconnecting the TV's Wi-Fi/Ethernet or approving a pending local prompt.

## macOS

In System Settings → Privacy & Security → Local Network, inspect access for the relevant host application if it appears. The requesting identity and permission behavior depend on how the tool is launched; absence of a Python entry does not prove denial. Apple documents command-line and daemon exceptions. [Apple Local Network settings](https://support.apple.com/en-gb/guide/mac-help/mchl211c911f/mac), [Apple TN3179](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

If a third-party network filter such as Little Snitch presents a prompt, review the local TV/discovery connection and approve it according to your policy, then retry the read. Doctor cannot inspect that filter's decision. For vault failures, use the signed-in desktop session, unlock Keychain and respond locally to its access prompt; never paste a pairing PIN or credential into an agent conversation.

## Windows

Use native Windows Python in the same signed-in account that paired the TV. In Windows Security → Firewall & network protection → Allow an app through firewall, review the actual Python executable used by this installation. Keep any exception limited to the trusted network profile you intend to use. Do not turn off the firewall as a diagnostic shortcut. Administratively managed rules may require your administrator. [Microsoft firewall settings](https://support.microsoft.com/en-us/windows/security/windows-security/firewall-and-network-protection-in-the-windows-security-app), [Microsoft app exceptions](https://support.microsoft.com/en-us/windows/security/firewall/risks-of-allowing-apps-through-windows-firewall)

Check the active network's Public/Private classification before assuming an exception applies. A Private designation is appropriate only for a network you trust. Windows Credential Manager access is per host/account; credentials from a Mac are not transferred automatically. WSL is not the native Windows vault workflow. Windows CI checks simulated diagnostics and native backend selection; Windows 11 TV/vault hardware recovery remains unverified.

## Error-specific next steps

| Observation/error | Next step |
| --- | --- |
| Missing/unusable dependency | Recreate an isolated environment and use locked installation; inspect `uv pip check`. |
| CREDENTIAL_STORE_UNAVAILABLE | Use the expected native backend and signed-in account; unlock/authorize it locally. Backend selection alone does not test access. |
| PAIRING_REQUIRED / AUTH_FAILED | Run explicit interactive `pair` locally, then retry `status`. Never automatically re-pair. |
| CONFIG_ERROR / failed registry check | Preserve the file first; follow [registry recovery](registry.md), and close competing processes before retrying. |
| DEVICE_BUSY | Allow the other operation to finish; do not delete a live lock file. |
| DEVICE_NOT_FOUND / empty discovery | Check LAN, TV connectivity and routing; try targeted discovery. |
| IDENTITY_MISMATCH | Verify the intended TV and explicitly pair it; do not trust an IP/name match alone. |
| TIMEOUT / NETWORK_ERROR | Inspect connectivity and permissions. Read failures can retry safely within their deadline; uncertain mutations must not be repeated automatically. |
| FEATURE_UNAVAILABLE / UNSUPPORTED_FEATURE | Inspect capabilities and current app/state; do not substitute a guessed control. |

See [pairing recovery](pairing.md) and [control outcomes](controls.md). Diagnostic output is intentionally limited; never attach native-vault exports, pairing logs or screenshots with private content as issue evidence.
