# Frontend modules

The dashboard uses native browser ES modules and vanilla JavaScript. There is no
bundler, framework or new npm dependency. FastAPI serves the files directly from
`static/`; the existing `static/*` package-data rule includes them in the wheel.
Open the application through its HTTP server, rather than opening index.html as a
local file. All imports are relative to their module, so channel control URLs work
without changing the module paths.

## Where to make changes

| File in `src/pacttsclone/static/` | Responsibility |
| --- | --- |
| `app.js` | Entry point, initial loading, snapshot rendering coordination, SSE handlers and locale refresh |
| `api.js` | REST requests, requester identity, CSRF headers, JSON/FormData handling and state refresh |
| `state.js` | Shared dashboard values and snapshot subscriptions |
| `dom.js` | DOM builders, action/error wrappers, translated labels and formatters |
| `navigation.js` | Tabs and shared Local/Twitch playback-control placement |
| `studio.js` | Local generation submission, job watching, result playback and Local OBS controls |
| `voices.js` | Voice upload, preparation, editing and rendering with draft preservation |
| `generation-settings.js` | Generation defaults, setting forms and saved-voice settings editors |
| `channels.js` | Channel configuration, commands, dashboards and playback queues |
| `twitch.js` | OAuth/device authorization, event rules, rewards and event history |
| `discord.js` | Webhook configuration, actions and status |
| `engines.js` | Engine install/activate controls and engine-specific generation options |
| `monitor.js` | Progress, timers, resources, residency, cancellation and panic |
| `history.js` | Pending generations and request history |
| `config.js` | Host configuration, setup-tab preference and optional sharing controls |
| `setup.js` | Setup readiness/progress and countermeasures dialog |
| `imports.js` | Weight discovery and optional personal-data imports |
| `updates.js` | Update check and summary |
| `help.js` | Lazy bug-guide video lifecycle |
| `events.js` | Existing shared SSE transport, reconnect and polling fallback |
| `update_panel.js` | Existing persistent updater/version-selection bridge |

## Initialization and updates

`index.html` loads the locale and existing SSE transport, then loads `app.js` with
`type="module"`. Module imports define functions and local data. The entry point
subscribes its renderer, calls each feature's `init…()` function once to register
listeners/timers, then starts asynchronous initialization. Navigation initializes
before other features can move or render the shared playback controls.

Features request REST refreshes through `api.refresh()`. Both REST refreshes and
SSE state packets call `state.updateState()`: it replaces `dashboard.state`, then
notifies subscribers with the changed sections. The entry point coordinates the
existing renderers and preserves section-specific updates. Feature modules do not
import or execute the entry point. Shared session/readiness/selection values live
in `state.js`; private timers, caches and draft bookkeeping stay in their owning
modules whenever they are not needed elsewhere. Importing state does not start
network requests, timers or DOM listeners.

No new dashboard globals are exposed. Existing `window.Locale`,
`window.StudioEventStream`, `studio-state`, `studio-resync` and `studio-updates`
contracts are retained for localization, the SSE transport and updater bridge.
The four SSE browser regressions now import module state through a test-only
handle rather than reading classic-script lexical globals.

REST endpoints, persistence, inference, integration execution, authentication and
OBS playback remain unchanged. This is a code-organization change, not a new
release or a claim about faster generation.
