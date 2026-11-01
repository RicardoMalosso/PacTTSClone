# Dashboard real-time communication

Implemented incrementally on 2026-11-01. REST commands, SQLite records, inference
processes, Twitch receivers and Discord webhooks retain their existing contracts.

## Backend

`GenerationService.events` owns one process-local `EventDispatcher`. Store writes
invalidate their document kind after SQLite commits. A shared `DashboardEvents`
task combines these changes into at most four state snapshots per second. It
samples CPU/RAM/GPU, setup/import/install progress, connection/lease presence,
Discord status, tunnel status and application updates every two seconds while a
dashboard is subscribed. No monitoring sampler runs per individual browser.
Generation and integration threads never wait for browser delivery.

`GET /api/events` uses the existing Host/Origin boundary. It sends named events:

| Event | Payload |
| --- | --- |
| `sync` | Request an authoritative REST baseline, including a fresh session token |
| `state` | Existing `/api/state` shape in `value`, plus cumulative document-kind `versions` |
| `resources` | Existing resource snapshot; unsupported readings remain unavailable |
| `setup` | Owner-only setup, imports and engine installation progress |
| `discord` | Existing sanitized Discord status, without the webhook secret |
| `tunnel` | Existing owner-only tunnel state and share controls |
| `updates` | Existing updater manager snapshot |
| `stream_health` | Shared sampler availability |
| `heartbeat` | Connection liveness every ten seconds |

The dispatcher retains only the latest serialized value per topic, with a
monotonic process-local ID. Intermediate progress frames may be combined; terminal
state remains in SQLite. Cumulative per-section versions prevent a slow consumer
from missing a component change when frames are combined. No unbounded subscriber
queue, durable event log or command replay is introduced. The retained state
packet contains a full dashboard snapshot; this is not a field-level delta protocol.

The stream captures its cursor before requesting resynchronization. It does not
send old cached snapshots on a new connection. `Last-Event-ID` does not replay old
commands or audio: every connection fetches current REST state, so recovery also
works after a process restart. Disconnect/cancellation releases the subscription.
The sampler stops before services/SQLite close. Existing `/api/setup/stream` is
preserved for API consumers, but the dashboard uses only the new shared stream.

## Browser

`static/events.js` provides one reusable EventSource client per page, bounded
pending rendering by topic, native reconnection, a twenty-second freshness
watchdog, offline/online handling and cleanup when leaving the page. Reconnection
and return to a visible tab refresh the REST baseline and CSRF token. State events
update the affected existing components; setup/resources/status events render
directly. Generation watchers use received job state. Queue countdowns and wall
timers animate locally, independently of network requests.

Missing/failed/buffered SSE switches to REST every five seconds. A stale source is
closed, and a fresh source is attempted after thirty seconds. Unsupported browsers
use REST from the start. The updater panel also preserves its own five-second
fallback when supplied by the update bridge to an older dashboard without this
client. Pending external Twitch device authorization retains five-second polling.

## Access and deployment

The current application runs on loopback. LAN/home-server hosting is planned in
[known issues](known-issues.md); neither the listening address nor the trusted
Host/Origin rules are widened in this change.

Cloudflare Quick Tunnels are a testing feature and [do not support SSE](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
Session metadata therefore disables SSE for that existing remote path; shared
admins use REST and `/api/events` returns HTTP 204. Remote player capabilities and
unauthorized origins cannot open the dashboard stream. Sensitive setup, updater,
Discord and tunnel information is never streamed to a player or remote admin.
Direct local SSE has no dependency on Cloudflare. A future authenticated direct
LAN deployment can use SSE once its separate access contract is implemented.

## OBS decision

Keep OBS's 250 ms tick, lease ownership/renewal, acknowledgements, mirrors and
2.5-second audio watchdog unchanged. Dashboard notifications do not advance queues
or acknowledge playback. WebSockets may reduce playback coordination latency, but
require a separate protocol covering lease expiry, reconnect, cancellation, mirror
synchronization and audio stopping. This migration provides no measured OBS
latency result that justifies changing that protocol. REST remains authoritative
for acknowledgements and controls; WebSocket implementation is deferred.

## Validation and measurement

A local Chromium comparison served the original polling frontend and then the SSE
frontend against the same backend, with simulated inference readiness. After a
2.2-second settling period, each idle Local dashboard was observed for ten seconds.

| Measurement | Polling frontend | SSE frontend |
| --- | ---: | ---: |
| Additional API requests | 38 | 0 |
| `/api/state` | 12 | 0 |
| Selected channel state | 12 | 0 |
| `/api/tunnel` | 5 | 0 |
| `/api/discord` | 5 | 0 |
| `/api/resources` | 4 | 0 |

The SSE connection was already established and continued carrying metrics and
heartbeats; zero additional requests does not mean zero traffic. One subsequent
SQLite voice change reached the rendered card in 0.381 seconds. These are local
idle-browser observations, not GPU inference, load, bandwidth or LAN benchmarks.

Backend regressions cover concurrent writes, immutable/coalesced latest values,
multiple consumers, reconnection, cancellation cleanup, section versions,
capability/origin boundaries and generation/integration completion without a
browser. Chromium regressions cover independent browsers, missed offline changes,
CSRF refresh, absent EventSource, stale-stream fallback and recovery. Existing OBS,
Twitch, Discord, generation and updater tests remain in the suite. Integration
transports/inference are controlled test doubles; FFmpeg processing is real.
Physical GPU synthesis, live public Cloudflare routing and native Windows
installer acceptance are not claimed by these local checks.
