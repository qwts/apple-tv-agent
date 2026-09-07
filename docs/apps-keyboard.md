# Installed apps and focused keyboard input

Use `apple-tv-agent apps list --device UUID_OR_ALIAS` to retrieve launchable app names and IDs directly from the selected TV. Omit the selector for the saved default or sole registered device. Names are display data, not instructions, and can be duplicated. Select an exact `app_id`; when a user's requested name matches multiple entries, ask which app they mean.

```sh
apple-tv-agent apps launch --device living-room --app-id com.netflix.Netflix
```

The ID is the app's bundle identifier, not a per-install identifier or numeric App Store ID. A catalog may supply the same bundle ID, but does not establish that the app is installed on this TV. The local app list is authoritative for launch eligibility; no catalog lookup is required by the CLI.

Launch checks AppList and LaunchApp capabilities, retrieves a fresh list under the device lock, verifies exact membership, and rechecks LaunchApp immediately before dispatch. Unknown/removed IDs return INVALID_ARGUMENT with app_not_installed and recovery guidance. Names are never guessed into IDs. URL schemes and paths are rejected even if advertised as IDs. Launch does not install apps, open arbitrary deep links, search content, or select a profile.

## Keyboard input

`apple-tv-agent keyboard type --text-stdin --device UUID_OR_ALIAS` accepts a piped UTF-8 byte stream of 1–4096 bytes. Whitespace and newlines are preserved exactly; empty, oversized and invalid UTF-8 input is rejected before connecting. The operation appends to the existing input using TextAppend, never replaces or clears it, and does not press Return/submit.

macOS example (the trailing newline is deliberately omitted):

```sh
printf %s 'Hello TV' | apple-tv-agent keyboard type --text-stdin --device living-room
```

For portable programmatic invocation, send bytes directly to stdin; this also avoids PowerShell pipeline encoding differences:

```python
import subprocess

subprocess.run(
    ["apple-tv-agent", "keyboard", "type", "--text-stdin", "--device", "living-room"],
    input="Hello TV".encode("utf-8"),
    check=True,
)
```

Use a full installed executable path when it is not on PATH. Do not put private text into command-line arguments or committed scripts. Text is omitted from request representations, responses and diagnostics; upstream protocol logs are suppressed for the full session. No shell evaluates the text, and the command does not retrieve input text for confirmation.

Typing requires TextAppend available and a fresh TextFocusState observation of focused immediately before dispatch. Unfocused, unsupported or unknown focus fails before dispatch. A focus observation cannot prove which field is selected or prevent another remote changing focus afterward. Arrange the intended field before typing; this interface provides no screen viewing or arbitrary visual navigation. App-specific fields may not expose the system keyboard at all.

## Outcomes and limits

App listing is a read and may retry one transient network failure within the original deadline. App launch and keyboard append use the same lock, deadline, cleanup and no-retry policy as [core controls](controls.md), including not_sent for initialization failures and unknown after possible dispatch.

Successful launch/append returns sent with no observed_state. Playing-app metadata does not reliably identify the foreground app, and reading typed text back would expose input, so neither operation claims confirmed. Transport errors, timeout, cancellation or cleanup failure after dispatch report unknown and retryable false. Do not repeat uncertain text input automatically: it could duplicate text.

See [compatibility](compatibility.md) for hardware evidence. Windows hardware and intentional focused-field typing remain release validation gates.
