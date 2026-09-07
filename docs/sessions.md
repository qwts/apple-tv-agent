# Status, capabilities and bounded sessions

After pairing, run `apple-tv-agent status --device UUID_OR_ALIAS` or `apple-tv-agent capabilities --device UUID_OR_ALIAS`. Omit the selector to use the saved default or sole registered device. No pairing prompt or control command is triggered by these reads. Authentication errors require an explicit local pairing command; they never automatically re-pair.

Status returns observed playback/power state, available media metadata, playing-app ID, position/duration, volume and keyboard focus. The app ID describes the app playing media, not necessarily the foreground app. `observed_at` is the UTC completion time of the observation; fields may have been read at slightly different times. A missing field stays null, with a fixed reason in `unavailable_fields`. Unsupported metadata does not hide an independently available power/volume observation. Missing, unavailable, unknown and invalid values are distinguished; NaN/out-of-range numeric values are not reported as valid state. A network failure while reading metadata is an error, not fabricated partial success.

Capabilities maps the transport-backed command names to `available`, `unavailable`, `unsupported` or `unknown`. Only `available` may be used to dispatch an action in the upcoming control implementation. Unknown/exceptional feature observations stay `unknown`. Keyboard type additionally requires confirmed keyboard focus; otherwise it is unavailable. Status and capabilities are implemented now; control/app/keyboard mutation CLI commands still return `FEATURE_UNAVAILABLE` until issues 006/007 land. This table describes transport capability, not completion of those CLI implementations.

## Identity, credentials and ownership

The service selects the registered UUID, acquires its cross-process lock and rereads the registry to account for a concurrent pairing/forget operation. It first tries the last IPv4 address, falls back to multicast if that address produces no candidates, and confirms protocol identity again in targeted discovery before reading secrets. A conflicting identity fails closed. Matching identity at a new address is acceptable; address/name alone never authorize credential use.

Credentials hydrate only in-memory pyatv settings. The session owns the pinned library's protocol setup handles before connection, then uses its normal facade and feature routing. Both connected and partially connected protocol setups are closed. Cleanup continues across individual close failures, closes HTTP resources and awaits cleanup tasks; cleanup failure cannot become a success response. Upstream credential-bearing logs are suppressed throughout discovery/connect/read/close; errors expose fixed classifications and no raw exception text.

## Timeouts and retries

`--timeout` is one monotonic deadline shared by selection, locking, discovery, connection, observation and cleanup. Up to one second (25% for timeouts below four seconds) is reserved for cleanup. Work stops before that reserve; cleanup does not start a new full timeout. Cancellation of a read closes the session and releases its lock. Deadline expiry reports `TIMEOUT`; user cancellation reports a canceled network operation. As with pairing, synchronous native-vault authorization may require a local OS dialog; native calls are not abandoned in background threads.

A transient connection/read network failure can trigger at most one retry. Each attempt owns a new session and repeats identity validation; it shares the original deadline. Authentication, pairing-required, protocol-response, busy-device and cleanup failures are not automatically retried. No retry begins after its work budget expires. This retry service rejects mutation commands.

A competing process receives `DEVICE_BUSY` when the bounded device-lock wait expires, or `TIMEOUT` if the command deadline expires first. Pairing and forgetting use the same UUID lock. Windows CI validates these semantics with simulated transport and spawned processes; Windows 11 status/capability hardware checks remain a release gate.
