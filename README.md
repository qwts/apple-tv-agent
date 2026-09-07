# Apple TV Agent

An implementation blueprint for an agent skill that controls a local Apple TV from a macOS or Windows computer.

**Status: discovery, device registry and native-vault pairing, status and capabilities implemented; control actions and agent skill pending.** Follow the [package setup](docs/cli-contract.md), [registry guide](docs/registry.md) and [interactive pairing guide](docs/pairing.md), and [status/capabilities guide](docs/sessions.md). Pairing runs in a local terminal with hidden PIN input; verified credentials remain in the native vault. Hardware support evidence and remaining Windows gates are tracked in [compatibility](docs/compatibility.md).

## Intended experience

Ask an agent to “pause the living room Apple TV,” “open an installed app,” “go home,” or “tell me what is playing.” The agent runs a local Python CLI, which communicates with the selected Apple TV over the LAN. Initial pairing requires a person to read a PIN from the TV and enter it in a local terminal.

The first release targets Apple TV HD and Apple TV 4K with macOS and native Windows. Exact supported OS, Python, and tvOS versions must be recorded after testing. The computer needs LAN access to the TV, a local command execution tool, and access to the paired user's credential store. Each computer pairs independently. No Apple ID password or developer account is part of the proposed workflow.

## Planned workflow

After the package and skill have been implemented and installed:

```text
apple-tv-agent doctor
apple-tv-agent discover
apple-tv-agent pair --device DEVICE_ID
apple-tv-agent devices alias --device DEVICE_ID --name living-room
apple-tv-agent status --device living-room
apple-tv-agent remote pause --device living-room
apple-tv-agent apps list --device living-room
apple-tv-agent apps launch --device living-room --app-id APP_ID
```

Pairing is interactive; other commands return JSON. The skill will explain how to invoke the CLI from both macOS shells and Windows PowerShell without assuming shell activation or a particular working directory.

## Implementation documents

- [DESIGN.md](DESIGN.md): scope, architecture, CLI contract, pairing, storage, failure handling, and validation.
- [Issue backlog](issues/README.md): ordered work with dependencies, agent implementation plans, and acceptance criteria.

Start with [001: validate the transport](issues/001-transport-spike.md). An implementing agent should read the design and its selected issue, complete dependencies, implement and test the issue, and update its status with evidence. Hardware-dependent work stays explicitly unverified until exercised on real hardware.

## Expected limitations

Commands depend on features exposed by the device and active app. Power and volume may also depend on the connected display or audio setup. The first release does not provide screen viewing, Siri, arbitrary visual navigation, content search inside streaming services, purchases, or remote access over the internet.

## Technical basis

The proposed transport is [pyatv](https://pyatv.dev/documentation/), accessed through its Python API behind a stable adapter. Runtime capability checks follow its [supported-features guidance](https://pyatv.dev/documentation/supported_features/). This project is independent of Apple and pyatv.
