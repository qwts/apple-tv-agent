# Optional LG screen observation: feasibility evidence

This is a follow-up experiment, not part of the packaged Apple TV CLI or its baseline support claim.

On 2026-09-07, local SSDP discovery identified an LG OLED65C2PUA. Its network services accepted SSAP over TLS WebSocket port 3001. Firmware reported 33.31.68 and product webOSTV 7.0. A minimal unsigned registration permitted foreground-app information but returned 401 insufficient permissions for screen capture. User-approved registration with the standard signed manifest used by existing webOS clients permitted capture. Pairing keys were kept in macOS Keychain; no key, private address, screenshot or profile information is committed.

Observed read endpoints:

- `ssap://system/getSystemInfo`: device model.
- `ssap://com.webos.service.update/getCurrentSWInformation`: firmware/product information, subject to permissions.
- `ssap://com.webos.applicationManager/getForegroundAppInfo`: LG foreground app/input, not the app inside HDMI.
- `ssap://tv/executeOneShot`: returned an imageUri on the TV's HTTPS service.

The downloaded 960×540 JPEG included the Apple TV's HDMI picture and its YouTube profile-picker and recommendation UI. A screenshot-guided Apple TV Select opened the requested profile; navigation then opened a requested recommendation, whose playback was independently confirmed through Apple TV metadata. No rooting, firmware change or app installation was used.

Some captures during transitions were black. Capture completion is not proof of usable visual context. HDMI input identification must be kept separate from Apple TV identity. The experiment used a local self-signed TLS connection; production work must define certificate/identity trust explicitly. Existing client manifests request broad remote permissions: the production pairing UI must describe them accurately, and screenshot-only execution must be constrained by the helper's command allowlist.

The probe and captures remain under the ignored `.local/lg-probe/` directory in the issue-007 worktree. This experiment does not establish Windows support, other LG model/firmware support, video-frame availability for every source, or protected-content capture. No continuous recording or telemetry was enabled.

References checked during the experiment: [bscpylgtv implementation](https://github.com/chros73/bscpylgtv), [webOS remote CLI screenshot command](https://github.com/griches/lgtvremote-cli). See the [implementation follow-up](../issues/011-lg-screen-observation.md).
