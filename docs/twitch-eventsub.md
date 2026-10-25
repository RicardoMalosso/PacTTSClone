# Twitch IRC and OAuth / EventSub

Each channel chooses one connection mode in **Twitch & OBS**. Existing saved
channels default to **IRC** and need no migration or authorization. IRC remains
anonymous and read-only, with `!command text` mapped to saved ready voices.

**OAuth** uses EventSub WebSockets for message commands and configured Channel
Points, Bits/Power-ups, subscriptions, gifts, resub messages, subscription endings,
followers, incoming raids and stream online/offline events. It creates no public
server, tunnel or webhook and never posts chat. A channel has only one active
transport; switching mode/settings closes the old receiver before replacing it.

## Setup on the host PC

1. Save the channel's Twitch login and choose OAuth mode.
2. Register an application at <https://dev.twitch.tv/console/apps> with **Public**
   client type, or use your already registered public application. Supply its
   **Client ID**, never a client secret. The project has no registered public
   Client ID bundled. `PACTTS_TWITCH_CLIENT_ID` can provide a default Client ID.
3. Select permission groups and click **Connect Twitch account**. Open the returned
   Twitch activation link/code and authorize **the broadcaster matching that channel**.
   A random viewer or moderator account cannot authorize someone else's broadcaster
   Bits/subscription/reward permissions. Every broadcaster authorizes separately.
4. Add event rules, choose a ready saved voice and save the channel with monitoring
   enabled. Message commands also work in OAuth mode using `user:read:chat`.
5. Review connection and individual event subscription errors in the dashboard.
   Selecting a rule without granting its permission produces a visible partial
   connection; authorize again with the missing group.

Permission groups: chat (`user:read:chat`), rewards (`channel:manage:redemptions`),
Bits (`bits:read`), subscriptions (`channel:read:subscriptions`), followers
(`moderator:read:followers`). Select only the groups needed. Raids and stream
online/offline need no additional event-specific scope. Twitch channel eligibility
still applies to Channel Points and monetization features.

The device flow runs in the host backend. Device codes and access/refresh tokens
never appear in UI state, SQLite request history, URLs to the app, or application
logs. Only Twitch's public activation URL and user code reach the host UI.
Authorization and reward-management endpoints are local-owner-only, including when
another administrator is connected through Cloudflare. Remote administrators may
configure channel actions and see event outcomes, but cannot access credentials.

On Windows saved credentials use current-user **DPAPI**. Other systems store a
separate credentials file with directory mode 0700/file mode 0600; that is access
control, not encryption. Tokens are refreshed with rotating refresh-token writes
and validated on startup and at least hourly during active use. No client secret
or hosted authentication service is required. Forget removes local credentials and
pending authorization; Twitch's Connections settings revoke the grant itself.
Forgetting/deleting while redemptions remain pending leaves those for manual
management in Twitch. Tokens are not portable between Windows user accounts.

## Event rules

| Kind | EventSub type | Suggested text |
|---|---|---|
| Channel Points | `channel.channel_points_custom_reward_redemption.add` | `{text}` |
| Bits / Power-ups | `channel.bits.use` | `{username}: {text}` or `{username} used {bits} Bits` |
| New subscription | `channel.subscribe` | `Welcome {username}` |
| Gift subscriptions | `channel.subscription.gift` | `{username} gifted {total} subscriptions` |
| Resub message | `channel.subscription.message` | `{username}: {text}` |
| Subscription ending | `channel.subscription.end` | `{username}'s subscription ended` |
| Follow | `channel.follow` v2 | `Welcome {username}` |
| Incoming raid | `channel.raid` | `{username} raided with {viewers} viewers` |
| Online/offline | `stream.online` / `stream.offline` | Explicit announcement text |

Supported placeholders: `{text}`, `{username}`, `{bits}`, `{total}`, `{tier}`,
`{months}`, `{viewers}`, `{reward}`. Templates do not execute code, access object
attributes or accept formatting specifiers. Text is never inserted as HTML.
Use one rule per event kind, or per reward ID for Channel Points. Bits has a minimum
amount per event. The app uses `channel.bits.use` alone, avoiding a duplicate cheer
subscription. Gift-recipient `channel.subscribe` events do not trigger the separate
new-sub rule; the aggregate gift event speaks once. Resub events require the viewer
to share their resub message. Extension Bits transactions are not included in this
Bits event. Power-ups may have no text: use an announcement template for them.

All speech uses the existing bounded generation queue, ready-voice checks, text
limit, per-user cooldown, moderation filters, cross-tab generation monitor and
channel OBS playback. Empty or rejected messages do not allocate inference work.
Incoming events and rejection/settlement errors appear in the channel event panel;
accepted speech also appears in normal request history. Bits/subscription payments
cannot be refunded by this integration; Channel Points settlement is separate.

## Rewards and refunds

**Load rewards** lists existing reward IDs and whether this registered application
can manage them. **Use reward** adds a mapping draft; choose its voice and save.
**Create TTS reward** creates a reward requiring viewer text, with automatic
Twitch fulfillment disabled, and adds a rule draft. Creating the reward is an
explicit Twitch mutation, separate from saving a rule.

App-manageable redemptions stay unfulfilled through generation and the OBS delay.
The coordinator's `played` acknowledgment triggers `FULFILLED`. Blocked requests,
queue failures, failed/cancelled generation, cancelled playback or interruption
trigger `CANCELED`, which refunds Channel Points. Network/API failures remain
pending with a visible error and retry after 60 seconds; terminal remote status
is reconciled if a previous successful PATCH response was lost. No active OBS
player means the reward remains pending until played or cancelled.

Twitch only lets the application that created a reward update its redemptions.
Rewards created in the dashboard or by another application can trigger speech,
but fulfillment/refunds remain manual in Twitch. Load or create rewards before
using automatic management so their manageable status is known.

Event delivery is at least once. Durable envelope IDs and separate redemption
IDs prevent duplicate work across reconnect/restart. Supplied timestamps older
than ten minutes are rejected. Seen/history records are bounded; unsettled events
are retained. Restart never replays stale speech. On a new EventSub connection,
managed rewards used by the channel's rules are queried for missed unfulfilled
redemptions and those older than the new connection are refunded without replay.
This recovery is bounded to 1,000 outstanding redemptions per reward per reconnect.
If it fails, the dashboard shows the recovery error; manage outstanding redemptions
in Twitch or reconnect to retry. The app does not claim lossless delivery for Bits,
subscriptions or other events during an offline gap.

## Transport and validation

New sockets subscribe through Helix after the welcome. Keepalive loss causes a
fresh socket and resubscription; Twitch-requested reconnects wait for the new
welcome before closing the old socket and transfer subscriptions without recreating
them. Only Twitch's secure EventSub host is accepted for reconnect URLs. Revocation
and partial subscription failures are visible. No commands are sent on the socket;
the WebSocket library handles control ping/pong.

Automated tests exercise OAuth polling, identity matching, scope errors, storage,
refresh, mode switches, subscription bodies, handoff, duplicates, moderation,
redemptions/refunds/recovery, UI persistence, locale and real FFmpeg/browser output
with simulated Twitch responses and explicit fake inference. Live consent, actual
paid Twitch events and real-model synthesis require separate acceptance; they are
not claimed by those tests. Windows CI executes the real DPAPI roundtrip.

Official references reviewed 2026-10-25:
- <https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow>
- <https://dev.twitch.tv/docs/authentication/validate-tokens/>
- <https://dev.twitch.tv/docs/eventsub/handling-websocket-events/>
- <https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/>
- <https://dev.twitch.tv/docs/api/reference/#update-redemption-status>
