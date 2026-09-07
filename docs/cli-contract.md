# CLI and JSON contract v1

Issue [002](../issues/002-package-contract.md) establishes the installable contract foundation. Issue [003](../issues/003-discovery-registry.md) adds live discovery and local registry list/alias/default operations. Issue [004](../issues/004-credentials-pairing.md) adds interactive pairing and local credential removal. Issue [005](../issues/005-session-status.md) implements status/capabilities; issue [006](../issues/006-core-controls.md) implements core controls; issue [007](../issues/007-apps-keyboard.md) implements installed apps and focused keyboard input; diagnostic commands return `FEATURE_UNAVAILABLE` with `details.reason = not_implemented`. Noninteractive pairing returns `INTERACTIVE_REQUIRED` first. The test-only fake adapter is dependency-injected; there is no CLI option that returns simulated device success.

Parsing arguments and registry list/alias/default commands do not load pyatv or access a native vault. Forget uses the native vault but sends no network commands. Discovery reads the LAN but does not pair or issue control commands. The separate [transport probe](compatibility.md) remains the opt-in hardware pairing/control feasibility tool.

## Install and validate

Python >=3.12 is the package baseline. Development resolution uses uv 0.12.10 and the committed universal `uv.lock`; it includes runtime and development dependencies with platform markers and artifact hashes. The tested pyatv pin is 0.18.0. Dependency compatibility and hardware compatibility are tracked separately in [compatibility.md](compatibility.md).

macOS, from the repository root (select an installed Python >=3.12):

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install uv==0.12.10
.venv/bin/uv sync --locked --python 3.14
.venv/bin/uv run --locked --no-sync apple-tv-agent --help
.venv/bin/uv run --locked --no-sync python -m apple_tv_agent --version
.venv/bin/uv run --locked --no-sync python -m pytest -q
.venv/bin/uv run --locked --no-sync python -m build --no-isolation
.venv/bin/uv export --locked --no-dev --no-emit-project > runtime-requirements.txt
.venv/bin/uv run --locked --no-sync python tools/check_wheel.py --requirements runtime-requirements.txt
```

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install uv==0.12.10
& .\.venv\Scripts\uv.exe sync --locked --python 3.14
& .\.venv\Scripts\uv.exe run --locked --no-sync apple-tv-agent --help
& .\.venv\Scripts\uv.exe run --locked --no-sync python -m apple_tv_agent --version
& .\.venv\Scripts\uv.exe run --locked --no-sync python -m pytest -q
& .\.venv\Scripts\uv.exe run --locked --no-sync python -m build --no-isolation
& .\.venv\Scripts\uv.exe export --locked --no-dev --no-emit-project --output-file runtime-requirements.txt
& .\.venv\Scripts\uv.exe run --locked --no-sync python tools/check_wheel.py --requirements runtime-requirements.txt
```

`check_wheel.py` creates a fresh temporary virtual environment in a path containing spaces, installs hashed runtime requirements and the built wheel, then runs both entry points outside the checkout. It checks version/help, structured errors, exit codes and the bundled schema. Artifacts remain local in `dist/`; no package registry publication is performed.

For deliberate dependency changes, edit `pyproject.toml`, run `uv lock`, then `uv sync --locked` and the validation commands. Commit metadata and `uv.lock` together. CI uses `--locked` so stale metadata/lock combinations fail instead of silently resolving new versions. To change one transitive dependency deliberately, use `uv lock --upgrade-package PACKAGE` and review the resulting lock diff. [uv documentation](https://docs.astral.sh/uv/concepts/projects/sync/)

## Command arguments

All commands support `--timeout SECONDS` (finite 1–120, default 15). It may appear before the command, after a command group, or after the leaf command; the last occurrence wins. Normal service execution has a deadline after arguments/stdin validation. Pairing will own separate human-input deadlines in issue 004.

Device selectors use `--device ID_OR_ALIAS` after the leaf command (or directly after `status`, `capabilities`, or `pair`). Selection is delegated to issue 003. IDs, aliases and app IDs must be nonempty, at most 256 characters, and contain no ASCII control characters. Argument abbreviation is disabled; unknown commands, actions and options are errors.

| Command | Extra arguments | Success `data` model |
| --- | --- | --- |
| `doctor` | Optional `--network` | `DoctorData`: version, Python, platform, checks |
| `discover` | Optional `--host` literal IPv4 | `DiscoveryData`: devices |
| `devices list` | None | `DevicesData`: devices, default_device_id |
| `devices alias` | Required `--name` | `AliasData`: aliases |
| `devices default` | None | `DefaultData`: default_device_id |
| `devices forget` | None | `ForgetData`: local_credentials_removed, registry_removed, default_cleared |
| `pair` | Interactive local terminal required | `PairData`: per-protocol results |
| `status` | None | `StatusData`: observation time, playback/power/metadata/volume/focus, unavailable_fields |
| `capabilities` | None | `CapabilitiesData`: observation time and per-command state/reason |
| `remote up/down/left/right/select/menu/home/play/pause/stop/next/previous` | Exactly one action | `ActionData` |
| `power on/off` | Exactly one action | `ActionData` |
| `volume up/down/set` | `set` requires finite `--level` in 0–100 | `ActionData` |
| `apps list` | None | `AppsData`: app IDs and names |
| `apps launch` | Required `--app-id` | `ActionData` |
| `keyboard type` | Required `--text-stdin` | `ActionData` |

Text input must arrive through piped stdin as valid UTF-8, 1–4096 bytes. Empty input is rejected; text is preserved exactly, including leading/trailing spaces and newlines. A terminal stdin is rejected to avoid an accidental blocking prompt. Text is excluded from request representations and response payloads. Do not pass PINs, credentials or text as command-line arguments. Windows callers should use a UTF-8 binary stdin stream; PowerShell's native pipeline encoding varies by shell version.

## Envelope and schema

Every ordinary command emits exactly one JSON object and a newline on stdout. JSON uses ASCII escapes for non-ASCII characters, which is valid UTF-8 and round-trips Unicode independent of Windows console encoding. Help/version are human-readable exceptions. Parser errors emit JSON with exit 2 and no raw argparse text. Future logs and interactive pairing prompts belong on stderr.

Every envelope contains these six keys; missing keys are invalid:

- `schema_version`: integer 1.
- `ok`: boolean; distinguishes the success and failure branches.
- `command`: canonical dotted command (for example `remote.pause`); may be null if parsing failed.
- `device_id`: resolved ID on device-specific success; null for global results or unresolved failures. Input aliases are never mislabeled as resolved IDs.
- `data`: the command-specific payload on success; null on failure.
- `error`: null on success; `{code, message, retryable, details}` on failure.

The machine-readable [response-v1.json](../schemas/response-v1.json) is generated from [models.py](../src/apple_tv_agent/models.py), checked for consistency in tests, validated with an independent JSON Schema implementation, and bundled inside the wheel. Regenerate it with `uv run --locked --no-sync python tools/generate_schema.py` after deliberate model changes. Unknown object fields are rejected by typed payload models and the schema.

Example response to the currently unimplemented `apple-tv-agent doctor`:

```json
{"schema_version":1,"ok":false,"command":"doctor","device_id":null,"data":null,"error":{"code":"FEATURE_UNAVAILABLE","message":"This feature is currently unavailable.","retryable":false,"details":{"reason":"not_implemented"}}}
```

Device and app names are untrusted strings, not instructions. Observation timestamps require timezone information; missing status values are null. `ActionData` has `outcome` (`confirmed`, `sent`, or `unknown`) and `observed_state` (a full status observation or null). A confirmed outcome requires a nonnull observation; services must additionally verify that the observation matches the requested effect. Errors after possible dispatch use `details.outcome = unknown`; core control services track this boundary. The contract layer never retries mutations.

## Error and exit mapping

| Code | Exit |
| --- | --- |
| `INVALID_ARGUMENT` | 2 |
| `DEVICE_NOT_FOUND` | 2 |
| `DEVICE_AMBIGUOUS` | 2 |
| `IDENTITY_MISMATCH` | 2 |
| `PAIRING_REQUIRED` | 3 |
| `INTERACTIVE_REQUIRED` | 3 |
| `AUTH_FAILED` | 3 |
| `CREDENTIAL_STORE_UNAVAILABLE` | 3 |
| `UNSUPPORTED_FEATURE` | 4 |
| `FEATURE_UNAVAILABLE` | 4 |
| `TIMEOUT` | 5 |
| `NETWORK_ERROR` | 5 |
| `DEVICE_BUSY` | 5 |
| `CONFIG_ERROR` | 6 |
| `INTERNAL_ERROR` | 1 |

Success exits 0. `retryable` defaults to false and means a safe automatic retry, not permission to repeat an uncertain mutation. Error messages come from a fixed catalog; raw parser, library and unexpected exception text is not printed. Error details are trusted structured application data, never raw library objects, credentials or user-entered text. Invalid service responses become `INTERNAL_ERROR`, preserving the single-JSON contract.

## Implementation seams

`Request` contains validated arguments; `ports.py` defines service, adapter, registry and credential-store protocols. Only future transport adapter modules will import pyatv. The default `ContractService` explicitly rejects unimplemented operations. Tests inject `FakeService` and a deterministic `FakeAdapter` to exercise success/error contracts without LAN access or secrets.

Issue 003 implements registry/discovery; 004 implements native credentials/pairing; 005–008 implement device services and diagnostics. Issue 001 remains open for Windows 11 hardware, native-vault persistence and remaining feature semantics. This merge establishes a versioned development contract using the proven library APIs; it does not waive those hardware release gates.

## Discovery and registry implementation

`discover`, `devices list`, `devices alias`, and `devices default` now execute their services. See [registry usage and recovery](registry.md). Pairing and `devices forget` are implemented; see [pairing and credential recovery](pairing.md). Status/capabilities are implemented; see [session behavior](sessions.md). Core controls are implemented; see [control mappings and outcomes](controls.md). App listing/launch and focused keyboard append are implemented; see [apps and keyboard](apps-keyboard.md). Diagnostic commands return `FEATURE_UNAVAILABLE` with `reason=not_implemented`; noninteractive pairing still returns `INTERACTIVE_REQUIRED`. Discovery never registers a device; interactive pairing explicitly registers its selected candidate.
