# 016: Build versioned GitHub releases for macOS, Windows and Linux

GitHub: https://github.com/qwts/apple-tv-agent/issues/30
Status: open
Priority: P1
Depends on: existing package/skill implementation; coordinate release gates with #1, #10 and #18

## Outcome

Users can select their OS and architecture on GitHub Releases, download a versioned bundle, extract it and run both CLI entry points without installing Python or development tooling. Include the portable agent skill, setup instructions and optional LG capture dependencies. This issue plans the pipeline and the platform work necessary to make the downloads usable; do not equate a successful archive build with validated device support.

## Agent implementation plan

1. Read DESIGN.md, pyproject.toml, the current CI workflow, tools/check_wheel.py and the release/hardware validation guides. Define the initial artifact matrix: macOS arm64 and x86_64, Windows x86_64, Linux x86_64. Record minimum supported OS versions and Linux libc/desktop requirements; evaluate additional architectures separately. Explicitly update DESIGN.md release scope, native credential requirements, CI matrix and hardware release gates from two host OSes to macOS, Windows and Linux; synchronize docs/hardware-validation.md and docs/release-validation.md with that scope. Update compatibility claims only with evidence.
2. Resolve Linux support before presenting its bundle as functional. NativeCredentialStore currently accepts only macOS/Windows backends. Implement and test an explicitly allowed secure Linux credential backend for both Apple TV and LG namespaces, including missing/locked keyring and headless-session behavior. Never fall back to plaintext storage. Extend diagnostics and setup documentation for session services, native libraries and network permissions. Keep native Linux discovery, pairing, reconnect and credential cleanup as explicit hardware gates alongside existing Mac/Windows gates.
3. Evaluate and choose a pinned bundling approach that includes the Python runtime and native dependencies; prototype it on every target host. Validate both apple-tv-agent and apple-tv-screen, dynamic keyring/pyatv imports, package resources and the JPEG decoder subprocess (currently launched with sys.executable -m). Adapt worker launching if the chosen bundle changes those semantics. Prefer an extractable directory bundle over installers unless evidence requires an installer. Document the decision and build inputs.
4. Build each OS/architecture artifact on an appropriate hosted GitHub runner with locked dependencies and pinned build tooling. Package executables/runtime, schemas, guides, the complete portable skill folder, optional screen support, and third-party license notices. Include wheel and source distribution as secondary developer downloads. Exclude all local registries, credentials, logs and captures. Never require real TVs, vault secrets or a self-hosted runner for ordinary release builds.
5. Define versioning from one authoritative project version, with matching v-prefixed release tags (for example v0.1.0a1). Fail on tag/version mismatch. Add PR/manual build validation that cannot publish. On a protected version tag, build and verify every required asset before creating a draft GitHub Release; prerelease versions must be marked prerelease. Restrict write permission to the publication job. Keep stable publication gated on recorded platform validation. Failed matrix jobs must not expose a partial public release.
6. Use predictable names such as apple-tv-agent-vVERSION-macos-arm64.tar.gz, apple-tv-agent-vVERSION-windows-x86_64.zip and apple-tv-agent-vVERSION-linux-x86_64.tar.gz. Generate SHA256SUMS and build provenance linking assets to the source commit and toolchain. Decide and document macOS signing/notarization and Windows signing requirements; use protected signing secrets when available and describe unsigned preview limitations accurately. Never imply checksums alone authenticate a publisher.
7. Add clean download/extract smoke tests on every target OS/architecture, including a path containing spaces and invocation from another directory. Run help, JSON error/schema checks, exported-skill validation and synthetic image decoding through the bundled executable. Verify no host Python/uv installation is needed, executable permissions survive extraction, and package resources resolve. Inspect archive contents and verify checksums. Keep LAN/native-vault tests separately opt-in.
8. Write release and user documentation: OS/architecture download table, checksum verification, extraction/start commands, skill installation with absolute executable paths, first pairing, platform prerequisites, upgrade and rollback, and uninstall. Upgrading/removing program files must preserve existing credentials/config unless explicitly removed through supported commands. Release notes must state tested platforms, known limitations and optional LG support independently.
9. Exercise the complete flow with a preview version: build, download, verify and run all platform bundles, then record sanitized results and native hardware gaps. Document failed-build recovery and reruns without silently overwriting published versioned assets; corrections require a new version. Keep #1/#10/#18 open where their validation is unmet.

## Acceptance criteria

- [ ] DESIGN.md and the hardware/release validation guides consistently define all three target platforms, secure credential requirements and per-platform release gates.

- [ ] GitHub Releases offers clearly named macOS arm64/x86_64, Windows x86_64 and Linux x86_64 bundles, plus checksums and version/commit provenance.
- [ ] Both CLI entry points and the portable skill work from an extracted bundle without separately installed Python or uv.
- [ ] Linux has a validated secure credential backend and actionable unsupported-session diagnostics; no plaintext fallback.
- [ ] All target archive smoke tests pass, including the bundled JPEG worker, spaces in paths and execution outside the extraction directory.
- [ ] Tag/version mismatch, failed builds and unauthorized publication are rejected; draft/prerelease/stable behavior is documented and tested.
- [ ] Bundles contain required resources and license notices, and no user data or credentials.
- [ ] Download, install, pairing, upgrade, rollback and removal instructions are verified; platform signing status and hardware support limits are explicit.

## Validation plan

Test workflow/version logic with valid, mismatched and prerelease versions; exercise matrix failure and rerun handling without publishing a stable release. Run bundle smoke tests on native hosted runners and verify a downloaded preview asset, not just the build directory. Record exact OS, architecture, version, commit and asset hashes. Record real-device pairing/reconnect/control and credential cleanup separately on each claimed platform. A missing host or native keyring session is not a passing result.
