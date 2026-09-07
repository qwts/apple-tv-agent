# Opt-in hardware release validation

Issue [010](../issues/010-validation-release.md) remains open until both native host baselines pass. Run this checklist manually on macOS and Windows 11 x64; hosted Windows Server CI cannot replace Windows 11, LAN or credential-store evidence. Never schedule these controls in unattended CI.

## Isolation and preparation

Use a dedicated local OS test account on each host. A new virtual environment alone does **not** isolate the registry or native credential store. Do not repoint HOME, copy production credentials, or delete an existing user's registry. Pair each account independently. Use a reference TV whose viewer has agreed to interruptions; record its original app, playback, volume and power state locally for restoration.

Record date, commit, OS version/architecture, Python and pyatv versions, TV model/tvOS, wired/Wi-Fi topology, and audio route (TV speakers, receiver or other). Omit addresses, identifiers, account names, media titles and credentials from shared evidence. Record whether each result came from JSON, a physical observation or both.

Follow the [locked setup](../skills/apple-tv-control/references/setup.md) from a fresh checkout in a path containing spaces. Below, `apple-tv-agent` and `python` mean the absolute executables in that environment, not an assumed PATH entry. Bare subcommands below are shorthand for that absolute CLI executable followed by the subcommand: for example, `discover --timeout 15` means `apple-tv-agent discover --timeout 15`. Run `doctor`; inspect each check, since completed diagnostics can exit zero even when a check fails.

## Baseline on each host

1. Run `discover --timeout 15`. Record candidate count and whether the reference TV appears. If empty, approve any locally displayed firewall prompt and repeat once; separately try `discover --host TV_IPV4`. Record multicast and targeted results independently, without claiming a cause from an empty scan.
2. In a local interactive terminal, run `pair --device CANDIDATE_ID` with a fresh candidate ID. Enter PINs only at hidden prompts. Record verified protocol names and any partial failure. Run `devices list` and retain the resulting registered UUID privately.
3. Exit the terminal, open a new one, then run `status --device UUID` and `capabilities --device UUID`. Success establishes fresh-process reconnect; it does not establish persistence across OS reboot. Repeat after a deliberate test-host restart and record that result separately.
4. With playback active and the capability available, send `remote pause --device UUID` once. Observe whether playback pauses; record the JSON outcome separately. Send `remote play --device UUID` once and observe restoration. Never repeat a possibly dispatched mutation automatically.
5. On a harmless visible menu, send one `remote right --device UUID`, observe the focus move, then one `remote left --device UUID` to restore it. Test `select`, `menu` and `home` separately with known screen context; record their actual behavior. A feature name alone is not evidence of Home semantics.

Baseline discovery, pairing, status, pause and navigation must pass on both host OSes before declaring release readiness. A failure blocks readiness; an untested baseline also blocks readiness.

## Capability and recovery matrix

Before each action inspect current capabilities. Record **pass**, **fail**, **unsupported**, or **not-tested** for every row. Use unsupported only when the structured response is `UNSUPPORTED_FEATURE`; temporary unavailability/unknown is not proof of permanent lack of support. Record `FEATURE_UNAVAILABLE` and the context; retest in suitable context or leave the hardware effect not-tested.

| Case | Procedure and expected evidence |
| --- | --- |
| Installed apps | `apps list --device UUID`; launch an exact returned ID using `apps launch --device UUID --app-id ID`. Observe foreground separately; `sent` alone is not visual confirmation. |
| Keyboard | Open a harmless search field manually. Pipe a short synthetic Unicode phrase into `keyboard type --device UUID --text-stdin`, preserving UTF-8 and whitespace. Observe append behavior and erase the phrase manually. Never use passwords or private text. Repeat outside a focused input: require refusal without dispatch. |
| Playback variants | Test stop/next/previous separately with disposable playback context and available capabilities; record actual media behavior and restore locally. |
| Volume | Record the route and initial level. Test one small step, its reverse, and an agreed absolute level with `volume set --level NUMBER --device UUID`. Observe audio effect; restore the original level. Do not assume every route supports absolute volume. |
| Power | With viewer agreement, `power off --device UUID`, then `power on --device UUID`. Record Apple TV and attached-display effects separately, including CEC behavior. Restore original state. |
| Multiple TVs | Pair two test TVs without configuring a default; a command without `--device` must return `DEVICE_AMBIGUOUS` without dispatch. Check explicit UUID and unique alias selection. If only one TV is available, mark not-tested. |
| Interrupted connectivity | Disable networking only on the test host, invoke a read, and restore networking. Require a bounded structured error and subsequent successful read. Test interrupted mutation only in a harmless context; uncertainty must not cause automatic replay. |
| Invalidated credentials | Revoke only this test account's pairing on the TV, then try status. Record structured failure and absence of automatic re-pairing. Re-pair interactively to recover. |
| Vault unavailable | Only in a disposable account where vault locking is supported, test a locked/unavailable vault and recovery. Never lock the active user's vault. If not practical, mark not-tested; backend selection is not vault access evidence. |
| Local removal | Follow cleanup below; verify every test credential is absent, rather than inferring deletion from the registry alone. |

## Upgrade and installation

There is no earlier stable release to migrate from. To validate an upgrade, record the exact old and candidate commits, use separate locked environments in the same test OS account, pair with the old revision, and close all its processes. Preserve a private registry backup. Invoke candidate `devices list` and `status`; verify the UUID, aliases/default and saved authentication survive without re-pairing. If the old version is unavailable, record not-tested. Unknown registry versions must return `CONFIG_ERROR` without reset; exercise corrupt/future-version fixtures through automated tests, not by corrupting a real user's data.

Run the [release reproduction commands](release-validation.md) for clean wheel installation. Copy the entire skill folder into a temporary client skills location and validate its links. Actual client discovery and a natural-language request are a separate manual check; fake-CLI walkthroughs do not prove client integration. Remove only the temporary skill copy afterward.

## Cleanup

In the dedicated account, run `devices forget --device UUID` for every test registration. Require success and confirm absence from `devices list`. Using the native credential manager, check that the corresponding `apple-tv-agent` UUID/protocol items are absent without displaying their values. Partial deletion is a failure; retain the UUID and follow [pairing recovery](pairing.md) rather than deleting the registry manually. Local removal does not revoke the TV's pairing: remove only test-client entries on the TV separately.

Restore networking and the TV's original state. Remove private test backups/logs and temporary skill copies after review. Preserve failed-cleanup notes until resolved. Never attach raw discovery/status output, screenshots, PINs, text, credential dumps or vault exports to issues.

## Sanitized evidence template

Copy one record per host into the issue; keep every unrun row explicit.

```text
Date / commit:
Host OS / architecture / Python / pyatv:
TV model / tvOS / topology / audio route:
Clean install / skill copy / actual client discovery:
Multicast discovery / targeted discovery:
Pairing protocols / fresh-process reconnect / OS-restart reconnect:
Status / pause / play / navigation / Home semantics:
Apps / keyboard / playback variants / volume / power:
Multiple TVs / connectivity loss / invalidated credentials / locked vault:
Upgrade from commit / UUID-alias-default preservation:
Local credential removal / TV pairing cleanup / state restoration:
Per-case result and JSON vs physical observation:
Remaining failures or not-tested cases:
```
