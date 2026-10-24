# V2 implementation contract — 2026-10-24

Supersedes v1 exclusions for cancellation, saved voices, settings, chat and OBS.

## Architecture

A persistent, spawned inference worker serializes expensive jobs. The server stays
responsive and samples resources independently. Cancellation terminates the worker
and its subprocesses, removes partial outputs, and starts a fresh worker for later
work. Completed audio/history and saved voices are retained. No training per voice.
SQLite stores configuration, voices, channels, jobs, moderation events and playback
items. Each voice has one original MP3, its filename, a title, saved transcript and
optional sanitized thumbnail. Blank transcripts become queued preparation jobs;
chat can only use a ready voice. Startup marks interrupted jobs cancelled and
interrupted playback stopped; it never replays stale work automatically.

Device settings use plain labels: Automatic, NVIDIA GPU/CUDA, CPU. ASR stays on
CPU. Device changes apply while the worker is idle; no silent CPU retry after GPU
OOM. Global hotkey is native RegisterHotKey on Windows. Unsupported platforms show
an explicit unavailable state and retain browser-focused shortcut/buttons.

## Measurement contract

Progress shows completed pipeline stages; downloads and operations without a
reliable denominator are indeterminate. Inference forward passes are activity,
not an invented completion percentage. UI shows wall timer, current stage duration,
CPU utilization, process RSS, system RAM and NVIDIA memory/utilization where
available. Unsupported metrics are null/N/A. Process CPU seconds count all worker
threads, so can exceed elapsed wall seconds; short external FFmpeg process CPU
is not included. GPU stage wall time includes CPU orchestration; CUDA allocation
and NVML device utilization do not imply exact per-job GPU busy time. Never label
CPU/GPU wall spans as mutually exclusive CPU/GPU compute seconds. JSONL logs retain
phase wall/CPU durations, device/hardware, peaks, timestamps and outcome, including
cancelled/failed jobs. UI exposes the same report after generation.

## Chat and moderation

Anonymous read-only IRC over TLS WebSocket (Twitch port 443), JOIN/PING/PONG,
capability negotiation, IRCv3 tags, reconnect/backoff, deduplication and bounded
queues. No chat posting, OAuth credentials, Bits or paid redemption claims.
Channel names and command keys are validated. Commands map to saved voice IDs.
Filtering occurs BEFORE allocating any generation job, including custom terms.
Unicode/case/spacing normalization plus whole-word/phrase matching limits accidental
substring matches. Mandatory basic slur list; optional profanity/strict lists.
This is a basic configurable lexical filter, not a guarantee against all evasion
or a complete implementation of Twitch policy. Bounded queue, message length and
per-user cooldown protect a streamer's machine from unbounded work.

## Playback

Per-channel FIFO playback, separate from the single generation queue. A rendered
item waits a configurable moderation countdown (default 5 s) when it reaches the
head and a player is present. OBS URL /{channel}; controls /{channel}/control.
The main UI also controls channels. A single expiring player lease prevents two
OBS/browser sources playing the same item twice. Playback needs start/end/error
acknowledgments; autoplay failures pause the channel with an enable-audio action.
Cancellation and global panic stop playing/countdown items; panic pauses channels
so the next item cannot speak immediately. Replay creates a new playback item,
reuses the existing MP3 and rechecks current filtering. A disconnected player is
interrupted, not silently replayed. Queue/history never contains unescaped HTML.

## Validation

Keep original deterministic coverage and real FFmpeg tests. Add SQLite persistence,
voice assets/transcription, configuration, worker kill/recovery, phase accounting,
filter-before-render, IRC framing/PING/reconnect, cooldown/dedupe, playback FIFO,
countdown/cancellation/lease/replay tests. Browser tests cover tabs, voice setup,
configuration, timers/progress, queue controls and the OBS player. Real model smoke
and live Twitch connectivity are reported separately from fake-engine tests.

## Added sharing and localization scope

User explicitly requested optional remote OBS/admin sharing after the core work.
A homepage button starts an ephemeral Cloudflare Quick Tunnel; another stops it.
cloudflared is reused from PATH or downloaded from Cloudflare's official GitHub
release into the configured data directory, verified against the asset SHA-256.
The origin Host is forced to a non-loopback sentinel; proxy requests can never be
mistaken for trusted loopback-owner requests. Remote API calls need an active
capability cookie and same-origin CSRF token. Admin and per-channel player keys
are independent, random, process-local and revoked on stopping/restarting sharing.
Keys are delivered in URL fragments and exchanged for Secure/HttpOnly/SameSite
cookies, not embedded into media query strings or access logs. Player capabilities
can only get their channel's audio, acquire/read playback and acknowledge playback;
they cannot read settings, history, logs, voice references or another channel.
Tunnel start/stop and share-key listing are local-only even for a remote admin.
Cloudflare relays shared audio/control traffic; model inference remains local.
No uptime guarantee or stable URL is claimed for Quick Tunnels.

Multiple OBS sources are supported: one lease holder coordinates the FIFO, while
other sources mirror currently playing audio using its start timestamp. Mirrors
cannot acknowledge/advance the queue. On coordinator loss, playback interrupts and
pauses rather than replaying stale speech. This allows the streamer's OBS and a
friend's remote OBS to receive the same channel without duplicating queue actions.

Locale starts from the browser/system preferred language, supports en-CA and
pt-BR, and saves a manual override in localStorage. Bottom controls show Canadian
and Brazilian SVG flags. UI strings are translated; voice names, original MP3
filenames, chat text, transcripts and machine-readable diagnostic report fields
are preserved verbatim. The transparent OBS page follows browser locale without
rendering permanent flag controls into the stream.
