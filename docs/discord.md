# Discord webhook design and setup — v2

## Scope

Replace the Discord Gateway bot, bot tokens, OAuth invites and incoming slash
commands with output-only webhooks. Mirror configured newly completed local/Twitch
speech MP3s; never upload references, history, transcripts, failed jobs or preparation.
Configuration is host-only and opt-in. Defaults: disabled, local selected, Twitch
unselected. Optional channel-name and voice-ID filters narrow output selection.

## Setup

1. Discord: Server Settings → Integrations → Webhooks → New Webhook.
2. Choose the receiving channel and Copy Webhook URL (Manage Webhooks permission).
3. PacTTSClone: Configuration → Discord integration; paste and save the URL.
4. Send test message; errors appear in the same panel.
5. Choose outputs, enable and save. Keep PacTTSClone running.

The URL grants posting access; keep it private. Webhooks cannot listen for
`!lula hello`, `/tts`, or any other Discord command. Existing Twitch commands
continue generating locally and can have their output mirrored to Discord.

## Delivery and security

Credentials live outside SQLite/imports, DPAPI-protected on Windows or mode 0600
elsewhere. Only canonical HTTPS discord.com webhook URLs are accepted. The sender
uses a fixed host, never follows redirects, disables mentions and suppresses
secret-bearing network exceptions. Test sends are explicit, host-only requests.
Legacy bot credentials/config are removed; no automatic conversion or activation.

A bounded background queue handles upload without blocking generation. Persistent
per-job delivery claims prevent duplicate completion callbacks. Errors remain
visible while successful MP3s remain available locally. Limit uploads to 10 MiB.
Rate limits and uncertain network failures are not retried automatically, avoiding
duplicate posts. Interrupted uploads are marked interrupted on restart, not replayed.
Reconfiguration/removal invalidates queued deliveries; an already-sending request
may finish. Shutdown waits for the bounded request timeout before closing SQLite.
Each new delivery includes the requester name, saved voice title and spoken message in a code block alongside the MP3. Mentions stay disabled. Long text is truncated to Discord limits; unavailable legacy names use an explicit fallback. Older History entries are never automatically uploaded.

Validation covers secret redaction/protection, URL restrictions, host boundaries,
source/voice/channel selection, completion delivery, duplicate suppression, queued
cancellation, multipart files, disabled mentions, upload errors and rate limits.
Live Discord delivery requires a user-provided webhook; tests use a controlled sender.
