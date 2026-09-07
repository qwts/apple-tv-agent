# Discovery and device registry

`apple-tv-agent discover --timeout 15` performs a bounded LAN scan. For targeted IPv4 discovery, use `apple-tv-agent discover --host 192.0.2.10`. IPv6 and hostnames are rejected. An empty scan is a successful result; a deadline exceeded is `TIMEOUT`. Discovery reserves a portion of the deadline for startup, service normalization and cleanup. Little Snitch, other firewalls, VPNs and multicast filtering can affect results. After approving a firewall prompt, rerun the command. No firewall settings are changed by the CLI.

Discovery includes only devices pyatv identifies as tvOS; Macs, speakers and unknown operating systems are excluded. Discovery returns candidate IDs, display names, protocol identifiers, address hints and pairing requirements. It never registers devices, accesses credentials, or changes a default. Candidate IDs hash the observed protocol identifier set; they are independent of address/name but may change when the advertised protocol set changes. Use a fresh scan when selecting a candidate for pairing. Names are untrusted display data and never selectors.

Registration is an internal operation for issue 004's pairing implementation. It assigns a UUID, records observed identity, and initially marks no protocols paired. The `pair` CLI remains unavailable until that issue lands; discovery alone does not populate the registry. A matching rediscovery preserves the UUID, aliases and default while updating the last address. A match needs at least one equal identifier under the same protocol and no disagreement among shared protocols. Partial advertisements may match; conflicting identities and observations bridging multiple registered devices are rejected. Normal actions must resolve identity before loading credentials. An unrelated device at a stored address cannot qualify by address alone. An explicit registration of a new identity creates a distinct UUID rather than inheriting the old device's secrets or aliases.

## Local commands

- `devices list` returns registered records and the saved default. `paired_protocols` is registry state, not a live credential-vault check.
- `devices alias --device UUID --name living-room` adds a unique, case-sensitive alias. Repeating it is idempotent. An alias cannot equal any registered UUID or another device's alias, or start with the reserved `candidate-` prefix. Unicode and spaces are preserved.
- `devices default --device UUID_OR_ALIAS` changes the default. No other operation automatically sets it.

Selection order is explicit UUID/alias, saved default, then sole registered device. Invalid explicit selections never fall back. Multiple eligible devices return `DEVICE_AMBIGUOUS` with IDs/name/address hints; no eligible device returns `DEVICE_NOT_FOUND`. A new candidate requires its explicit candidate ID for pairing. Device control, credential removal and pairing remain separate implementation issues.

## Storage and recovery

The version 1 nonsecret JSON file is `registry.json` under `platformdirs.user_config_path("apple-tv-agent", appauthor=False, roaming=False)`:

- macOS: `~/Library/Application Support/apple-tv-agent/registry.json`
- Windows: `%LOCALAPPDATA%\apple-tv-agent\registry.json`

The file contains schema version, registered UUIDs, display names, protocol identifiers, aliases, last addresses, paired protocol labels and a default UUID. PINs and credential values never belong here. Registry operations use a separate `registry.json.lock` with the pinned [filelock](https://py-filelock.readthedocs.io/en/latest/) native platform backend. The lock covers read/validate/modify/write, waits at most five seconds by default and is cancellable. Contention returns `DEVICE_BUSY` (or `TIMEOUT` if the command deadline expires first). This is intended for local storage, not a network-shared configuration directory.

Writes validate the complete state, flush and fsync a temporary file in the same directory, then atomically replace the registry. Failure before replacement leaves the previous file intact. Process termination releases the OS lock; a crash can leave a `.registry-*.tmp` file that is ignored. Sudden power loss/filesystem failure has no stronger guarantee than the host filesystem provides.

For `CONFIG_ERROR`, preserve the registry before recovery; the CLI does not reset corrupt data or downgrade unknown versions. Stop other CLI processes, copy the original file to a backup, and inspect the schema version and access permissions. Restore a known valid backup or use a compatible package for a newer schema. Remove an orphan temporary file only while no registry operation is running. Do not delete an active lock file: the file's presence does not indicate it is locked. Do not reset UUIDs casually: future native credentials are keyed by UUID, and discarding the registry will not revoke or erase those credentials. See issue 004 for coordinated removal.


The recovery guide is included in wheels as the package resource `apple_tv_agent/docs/registry.md`. Read it offline with the same Python interpreter used for the CLI:

```sh
python -c "from importlib.resources import files; print(files('apple_tv_agent').joinpath('docs/registry.md').read_text(encoding='utf-8'))"
```

A registry containing an alias with the reserved `candidate-` prefix is invalid. For pre-release registries that used such aliases, stop CLI processes, preserve a backup and rename only the conflicting alias to a nonreserved value; keep the UUID and protocol identifiers intact.
