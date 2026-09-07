# Optional LG capture and HDMI association

`apple-tv-screen` now supports explicit HDMI bindings, one-shot capture, and local artifact cleanup. It never switches the LG input or sends an Apple TV control. [Pair the LG](lg-pairing.md) and Apple TV independently first. Baseline remote commands do not require the optional image decoder.

## Install and associate

Use the reviewed checkout's absolute uv executable with `sync --locked --extra screen --project ABSOLUTE_REPO_PATH`. The optional extra pins Pillow 12.3.0; no global install is needed. For developer tests, install this extra too. A base-only installation returns a fixed CONFIG_ERROR before networking if capture is requested without the decoder.

Use the absolute `apple-tv-screen` executable (abbreviated below). On PowerShell, place `&` before a quoted executable path.

```text
apple-tv-screen devices
apple-tv-agent devices list
apple-tv-screen bind --device LG_UUID --apple-tv APPLE_TV_UUID --hdmi 4
apple-tv-screen bindings
apple-tv-screen capture --binding BINDING_UUID
apple-tv-screen discard --observation OBSERVATION_UUID
apple-tv-screen cleanup
apple-tv-screen unbind --binding BINDING_UUID
```

The user chooses both registered UUIDs and HDMI input 1–4. Binding checks both registrations and asks the authenticated LG for its capture service URL; this can cause the TV to create a one-shot frame, but bind does not download or retain image bytes. URLs must be HTTPS on the selected literal IPv4 address, with no userinfo, fragments, control characters or redirects. Binding inspects that service's certificate. If it equals the previously trusted SSAP certificate, the existing trust applies. A different image-service certificate requires explicit local-terminal approval before being saved; noninteractive callers receive INTERACTIVE_REQUIRED. The local prompt identifies the image service and port. No saved client key is sent to the image server.

Bindings persist in `screen-bindings.json` alongside the registries. Each records the Apple TV/LG/HDMI association and image port/certificate pin. Updating the same pair's input or image trust creates a new binding UUID; repeating the exact association/trust is idempotent. This is an explicit user association, not automatic physical-source identification. Unknown, removed or unpaired devices cannot capture through an old binding. Unbind does not delete TV credentials or outstanding screenshots; discard those separately.

## Capture and uncertainty

Capture rediscovers the LG identity, pins SSAP before reading a saved credential, checks the foreground HDMI input, requests one frame, and downloads only from the saved same-TV HTTPS port with its certificate pin. It rejects redirects, certificate changes, off-device URLs and input mismatch. Inputs are checked again after the download. No automatic screenshot retry loop is provided. An empty discovery result produces DEVICE_NOT_FOUND rather than claiming that the device identity changed.

The request has a shared monotonic timeout. Image acquisition/validation also uses a short frame budget; the resulting observation expires at most ten seconds after acquisition starts. JPEG bytes are streamed completely under a 10 MiB cap. A separate Python process decodes the JPEG using Pillow, rejects missing/truncated data, limits dimensions to 8192 and pixels to 16 million, and is killed/reaped on timeout or cancellation. The decoder receives bytes on stdin and emits only fixed metadata; it writes no image file. No Pillow import or image decoding occurs during normal baseline CLI use.

On success, `data` follows the bundled observation-v1 schema: binding, host start/receive/expiry timestamps, before/after LG input, quality, and image metadata including an absolute path, SHA-256, dimensions and deletion target. A near-black decoded image is marked `black`; other valid images are `usable` for inspection, not automatically evidence of the desired UI. A transitional or stale TV frame can still decode successfully. `source_frame_time` remains null; host acquisition time does not prove when the TV rendered the frame. Identical hashes can represent a static UI or stale content and cannot distinguish them. Before acting, check expiry/input/binding and inspect the image itself. A visual inference does not rewrite an Apple TV action's transport outcome.

The experimental envelope still has `schema_version`, `command`, `ok`, `data`, `error`. `bind` returns a binding record; `bindings` returns the local binding collection; `capture` returns an observation; `discard` returns observation_id/deleted; `cleanup` returns deleted_count; unbind returns binding_id/removed. Capture errors use fixed input-mismatch/invalid-image/missing-extra guidance with existing error codes. Raw image URLs, client keys, peer payloads and image content are never included in errors.

## Artifact privacy and lifecycle

Artifacts live under the platformdirs user data directory for `apple-tv-agent`, in a private `captures` subdirectory. POSIX permissions are 0700 for the directory and 0600 for files. Windows replaces the directory DACL with a protected current-user SID grant inherited by new files; it does not rely on chmod for Windows privacy. Symlink/reparse directories and inventory files are refused. These controls protect against other ordinary local accounts, not administrators or malicious processes running as the same user.

The inventory records UUID ownership and five-minute deletion targets. Files have UUID-derived names; discard accepts only an observation UUID and never an arbitrary path. The inventory is written before a new file so interrupted writes remain recoverable. Existing filename collisions are not adopted or overwritten. Partial-write failures attempt cleanup; failures remain errors, never successful captures. Deletion removes owned files before removing inventory entries, making interrupted cleanup retryable.

Expired artifacts are removed at the start of each capture and by `cleanup`. **Five minutes is a cleanup target, not a background deletion guarantee.** Without another invocation a file can remain on disk longer. Agents should discard immediately after inspection. A failed cleanup is reported rather than silently ignored. Unknown UUID files are not deleted merely because they exist in the directory. Never commit or upload screenshots, raw status/discovery output or capture URLs.

The CLI does not return a path for malformed images or input mismatch. If an error occurs after saving, capture attempts owned-artifact deletion. Corrupt inventory/binding data produces CONFIG_ERROR; preserve it privately before recovery and do not use baseline registry reset instructions. Do not manually unlink active lock files. The reference helper leaves no always-on process or automatic capture loop.

## Validation and remaining limits

Offline fixtures cover input mismatch, changed bindings, image-service trust, redirects/off-device ports/certificate errors, full chunked reads, oversized/truncated/black images, decoder timeout cleanup, private artifact creation, expiry/idempotent discard and refusal to delete unowned paths. CI runs with the optional extra on macOS/Windows and smoke-checks both base and optional wheel installation. Synthetic skill fixtures exercise usable, black, expired, wrong-input and structured-error outcomes; they are not an independent model evaluation or proof of visual target selection.

Native Windows TV capture and the complete baseline hardware release matrix remain unverified. Compatibility applies only to recorded host/model/firmware evidence. Do not infer all LG models or protected-content support from one successful frame.

References: [Pillow image loading and validation](https://pillow.readthedocs.io/en/stable/reference/Image.html), [pinned Pillow release](https://pypi.org/project/pillow/12.3.0/). The public LG SSAP manifest and provenance are documented in [pairing](lg-pairing.md).

## Validation evidence (2026-09-07)

On macOS 26.6.2 / Python 3.14.7, the production CLI bound the paired reference OLED65C2PUA to the registered Apple TV on HDMI 4. Its image service used the already approved certificate. A fresh CLI process returned a fully decoded 960×540 JPEG with empty stderr; visual inspection confirmed HDMI video content. UUID-based discard succeeded and filesystem inspection confirmed deletion. No screenshot, capture URL, device identifier or key is committed. Reference firmware was previously recorded as 33.31.68.

Local validation: 597 tests passed, two platform-specific skips; Ruff and skill checks passed. Source/wheel builds and clean installation checks passed both without the optional decoder and with the screen extra. Synthetic skill walkthroughs validate command/metadata handling, not independent model vision. Native Windows pairing/capture and visual-navigation hardware validation remain open under #18/#10/#1.
