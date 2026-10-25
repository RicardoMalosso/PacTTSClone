# PacTTSClone RC6 — Twitch IRC and authorized events

Per-channel connection choice preserves anonymous IRC message commands and adds
OAuth/EventSub for chat, Channel Points, Bits/Power-ups, subscriptions, gifts,
resub messages, follows, raids and stream lifecycle. Configurable event-to-voice
rules reuse moderation, queues, monitoring and OBS playback.

Host-only device authorization needs a registered public Twitch Client ID and
matching broadcaster consent. No client secret or hosted callback is required.
Windows credentials use DPAPI. Includes permission/connection diagnostics,
reward listing/creation, managed fulfillment after playback, failure refunds,
durable duplicate suppression and recovery of missed managed redemptions without
replaying stale speech. Rewards created elsewhere require manual settlement.

See docs/twitch-eventsub.md for setup, permissions and limitations. Automated
Twitch tests use simulated service responses and explicit fake inference; live
consent, real paid events, OBS CEF and physical CUDA require separate acceptance.
Installer publication remains gated by the complete Windows acceptance workflow.

Optional Configuration imports are available before setup readiness: transfer
verified large model weights separately from configuration/voices/completed audio.
Model copy/move checks pinned hashes; personal-data migration retains the source,
backs up metadata, remaps IDs and does not replay old queues.
