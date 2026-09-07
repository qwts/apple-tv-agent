# 015: Complete LG one-shot capture, HDMI binding and skill integration

GitHub: https://github.com/qwts/apple-tv-agent/issues/28
Status: in review

Parent #18; depends on merged #26.

## Outcome
Complete the optional LG observation feature with explicit Apple TV/HDMI binding, trusted one-shot JPEG capture, private artifact ownership/cleanup and portable skill guidance.

## Agent implementation plan
1. Persist explicit bindings separately from LG trust and Apple TV registries. Validate both registered UUIDs and HDMI input; discover the capture image service through authenticated SSAP. Permit same-TV HTTPS only, inspect its certificate and require local approval if different from the already trusted LG certificate.
2. Reuse identity-before-key and pinned SSAP. Check foreground input before/after capture, enforce same-host/saved-port image URLs, reject redirects, pin HTTPS and stream the complete byte-bounded body under a shared deadline.
3. Add optional pinned Pillow dependency for full JPEG validation, pixel/dimension limits, truncated-file rejection and conservative blank-frame handling. Return the versioned observation result, never visual claims derived from metadata.
4. Create private local artifacts with an owned inventory, five-minute retention target, explicit UUID-based discard and expired-file cleanup. Reject path traversal/symlink ownership tricks and enforce native Windows ACLs; no continuous recording.
5. Extend the experimental CLI, package resources and validate base installation without image dependencies plus optional capture installation. Add fake network/image/cleanup tests across the host matrix.
6. Update the self-contained skill for observe/identify/one action/observe, ambiguity, untrusted screen text, stale/black frames and cleanup. Hardware-check one-shot capture and deletion on the reference Mac; record Windows hardware as not-tested.

## Acceptance criteria
- The reference paired LG/HDMI association yields a decoded local image with pinned transport and no leaked credentials/capture URLs.
- Invalid/mismatched/oversized/truncated frames and off-device/redirect/certificate changes fail safely.
- Artifact expiry/discard and privacy controls are testable and documented.
- Skill can invoke documented capture, interpret visual context conservatively and clean up after use.
- Cross-platform offline checks pass; remaining native Windows release gates stay explicit under #18/#10/#1.

## Validation evidence (2026-09-07)

On macOS 26.6.2 / Python 3.14.7, the production CLI bound the paired reference OLED65C2PUA to the registered Apple TV on HDMI 4. Its image service used the already approved certificate. A fresh CLI process returned a fully decoded 960×540 JPEG with empty stderr; visual inspection confirmed HDMI video content. UUID-based discard succeeded and filesystem inspection confirmed deletion. No screenshot, capture URL, device identifier or key is committed. Reference firmware was previously recorded as 33.31.68.

Local validation: 597 tests passed, two platform-specific skips; Ruff and skill checks passed. Source/wheel builds and clean installation checks passed both without the optional decoder and with the screen extra. Synthetic skill walkthroughs validate command/metadata handling, not independent model vision. Native Windows pairing/capture and visual-navigation hardware validation remain open under #18/#10/#1.
