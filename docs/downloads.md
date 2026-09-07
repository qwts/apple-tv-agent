# Downloadable release bundles

The release workflow builds self-contained development-preview bundles. Download assets from a published [GitHub Release](https://github.com/qwts/apple-tv-agent/releases); drafts are visible only to maintainers. A green build is not native TV compatibility evidence. See [release validation](release-validation.md) for outstanding hardware gates.

| Download suffix | Target |
| --- | --- |
| `macos-arm64.tar.gz` | Apple Silicon Mac; build/smoke baseline macOS 15 |
| `macos-x86_64.tar.gz` | Intel Mac; build/smoke baseline macOS 15 |
| `windows-x86_64.zip` | Windows x64; Windows 11 is the intended desktop target, hosted smoke tests use Server 2022 |
| `linux-x86_64.tar.gz` | Linux x64; Ubuntu 22.04/glibc 2.35 or newer is the build baseline, musl/Alpine is not supported |

Older operating systems and other architectures are unverified. Linux pairing needs a signed-in desktop D-Bus session and an unlocked Secret Service provider such as GNOME Keyring; install these through your distribution. Headless sessions without this service cannot pair or reuse saved credentials. There is no plaintext fallback. The CLI does not start/unlock a keyring service automatically.

## Verify and extract

Choose the version and architecture explicitly. Download its archive and `SHA256SUMS` from the same release. On macOS use `shasum -a 256 ARCHIVE`; on Linux use `sha256sum ARCHIVE`; in PowerShell use `Get-FileHash ARCHIVE -Algorithm SHA256`. Compare the complete digest with that archive's line in `SHA256SUMS`. Checksums detect altered bytes; they do not independently authenticate the publisher. `PROVENANCE.json` and each bundle's `BUILD.json` record source/version/toolchain identity, not a cryptographic attestation.

Extract the entire tar.gz or zip into a stable directory you own. Keep both executables beside `_internal`; moving only an executable breaks its runtime. Python, uv and a compiler are not required. Preview bundles have no publisher code signature or notarization (Mac binaries have ad-hoc signatures). OS trust prompts may apply. Verify the source and use normal OS approval controls; do not disable system-wide security protections.

macOS/Linux:

```sh
"/absolute/path/Apple TV Agent/apple-tv-agent" --version
"/absolute/path/Apple TV Agent/apple-tv-agent" doctor
"/absolute/path/Apple TV Agent/apple-tv-agent" discover
```

Windows PowerShell:

```powershell
& 'C:\path\Apple TV Agent\apple-tv-agent.exe' --version
& 'C:\path\Apple TV Agent\apple-tv-agent.exe' doctor
& 'C:\path\Apple TV Agent\apple-tv-agent.exe' discover
```

`doctor` may complete while individual checks fail; inspect its results. Choose a discovery candidate, then run `pair --device CANDIDATE_ID` in your own local terminal and enter TV PINs only at hidden prompts. Each computer pairs independently. Allow requested local-network permissions when appropriate; the application never changes firewall rules itself.

## Agent skill and LG observation

Copy the entire `skills/apple-tv-control` directory into your agent client's supported skills directory. Tell the agent the absolute paths of both bundled executables. The client must support local command execution; skill installation alone does not prove client discovery. Both tools run from any working directory. See the portable skill's references for controls and pairing.

The `apple-tv-screen` executable includes optional LG decoding support. LG pairing, HDMI binding and screenshot privacy are separate from Apple TV control; follow [LG capture](lg-capture.md). No continuous screen capture starts on install.

## Upgrade, rollback and removal

Extract a new version beside the old version, stop old CLI processes, check `--version` and `doctor`, then update the agent's absolute executable paths. Keep the previous bundle for rollback. Configuration and native credentials are stored outside the program directory and remain intact. Do not run both versions concurrently during migration; preserve a private config backup before an upgrade. Rollback must respect registry schema compatibility; an unknown schema fails without resetting user data.

Delete an old extracted directory to remove its program files. This does not delete native credentials or registries. For explicit credential removal, first use the documented `devices forget` and LG `forget` commands while the executable is still available; discard owned screenshots and remove any skill copy separately. Do not delete unrelated vault entries or export pairing keys.
