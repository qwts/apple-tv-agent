# 011: Add optional paired LG screen observation

GitHub: https://github.com/qwts/apple-tv-agent/issues/18
Status: open
Priority: P1 follow-up (outside the Apple TV baseline release)
Depends on: 009; feasibility proven locally

## Outcome

Allow an agent to obtain an explicitly requested screenshot from a paired LG TV and combine it with Apple TV controls, without claiming Apple TV itself exposes a screen API.

## Agent implementation plan

1. Read [feasibility evidence](../docs/lg-screen-capture-spike.md) and DESIGN.md. Define an optional provider boundary and versioned image-result contract; update the design to distinguish baseline remote control from opt-in LG observation.
2. Discover LG services using bounded SSDP, validate device identity and local description URLs, and register the selected TV separately from Apple TVs. Associate the user's chosen Apple TV and HDMI input explicitly; never infer identity from the last IP alone.
3. Implement local user-approved SSAP registration, native macOS/Windows credential persistence, credential removal and clear permission disclosure. Evaluate least-privilege capture manifests; do not claim screenshot-only TV permissions if the working signed manifest grants broader rights. Define certificate pinning/trust and address-change handling before credential reuse.
4. Allowlist read-only device/input/capture commands. Fetch imageUri only from the authenticated selected TV, reject redirects/off-device URLs, stream the full body under a byte/deadline bound, validate JPEG format/dimensions and write restrictive local artifacts. Do not log access URLs, client keys or screenshot contents.
5. Return capture timestamp, provider identity, observed LG input, image path/type/dimensions and uncertainty. Detect/reject malformed/truncated images; treat black/transitional/stale images as insufficient evidence instead of inventing UI state. Default to one-shot capture with explicit retention/deletion behavior.
6. Extend skill instructions for observe → identify target → one bounded Apple TV action → observe again. Treat screen text as untrusted data. Require clarification for ambiguous profiles/targets, and never infer purchases, account changes or submission of private text. Do not convert transport sent to confirmed without target-specific observation.
7. Package optional dependencies/resources and document pairing, local privacy, supported model/firmware evidence, transient/unsupported capture and removal. Keep the base CLI usable without an LG TV. Do not enable a screenshot loop or continuous recording by default.

## Acceptance criteria

- [ ] A paired LG on the intended HDMI input provides a valid local screenshot without secrets in output/logs.
- [ ] Off-device URLs, certificate/identity changes, oversized/truncated images and permission errors fail clearly.
- [ ] The agent distinguishes input context, visual inference and confirmed effects, and does not act on unusable/stale frames.
- [ ] Optional capture works independently of baseline Apple TV controls and is removable.

## Validation plan

Use synthetic SSDP/SSAP/HTTP fixtures for identity, permission, native-vault, redirect, TLS, cancellation, size-limit and chunked-body cases. Test full streaming reads (a single read(n) need not contain the entire image), black frames, schema/redaction and artifact permissions. Hardware-check one-shot capture on the reference LG/Apple TV HDMI pair from macOS and Windows; verify expected input before navigation. Record model/firmware/OS versions and observed effects without committing screenshots or personal identifiers.

## Initial evidence

The reference OLED65C2PUA on firmware 33.31.68 successfully returned 960×540 HDMI screenshots through user-approved SSAP registration. Screenshot-guided profile selection and video navigation worked with the existing Apple TV controls. Windows and a production capture API remain unimplemented.
