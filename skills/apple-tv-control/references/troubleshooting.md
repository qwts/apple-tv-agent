# Recovery without guessing

| Result | Agent response |
| --- | --- |
| DEVICE_AMBIGUOUS | Show the relevant UUID/alias choices and ask which TV. Do not act or change the default. |
| DEVICE_NOT_FOUND | Verify the selector. Discover if needed; never fall back from an invalid explicit selector to another TV. |
| INTERACTIVE_REQUIRED / PAIRING_REQUIRED / AUTH_FAILED | Give the local interactive pairing command from [setup](setup.md). Keep PINs and credentials out of chat. No automatic re-pairing. |
| CREDENTIAL_STORE_UNAVAILABLE | Ask the user to unlock/authorize the native vault in their local desktop session. Doctor only verifies backend selection, not access. Never export credentials or switch to plaintext storage. |
| FEATURE_UNAVAILABLE / UNSUPPORTED_FEATURE | Explain the unavailable action and current capability. No guessed alternate, toggle or protocol call. |
| DEVICE_BUSY | Let the current command finish. Do not delete an active lock file. |
| TIMEOUT / NETWORK_ERROR after possible dispatch | State uncertainty; no automatic action retry. Read status if it can clarify the effect. |
| CONFIG_ERROR | Preserve the registry and consult the package's bundled registry recovery guide. Do not reset it automatically. |
| Missing/incompatible dependency | Use doctor and reinstall the locked environment from [setup](setup.md). If the CLI cannot start, use its Python environment to repair installation first. |

Run doctor locally first; --network is an explicit opt-in scan. Candidate replies do not prove control/authentication; no replies do not prove a firewall failure. Check TV connectivity, VPN routes and guest/client isolation. A known LAN IPv4 can be tested with discover --host IPV4; identity checks still apply later.

macOS: System Settings → Privacy & Security → Local Network may list the host application. Command-line launching has exceptions; a missing Python entry is not proof of denial. Review any local network-filter prompt and retry a read after the user resolves it. [Apple guidance](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

Windows: Windows Security → Firewall & network protection → Allow an app through firewall lets the user inspect an exception for the actual Python executable on the intended trusted profile. Use native Windows and the account that paired the TV. Do not disable the firewall or change network classification automatically. [Microsoft guidance](https://support.microsoft.com/en-us/windows/security/windows-security/firewall-and-network-protection-in-the-windows-security-app)

The installed package contains fuller guides under apple_tv_agent/docs, accessible via importlib.resources without relying on the checkout. [Repository recovery guide](https://github.com/qwts/apple-tv-agent/blob/main/docs/troubleshooting.md)
