# Local Discord integration

PacTTSClone runs a dedicated Discord bot on the host PC. The bot receives slash
commands over Discord's Gateway, generates speech through the existing local
queue, and uploads the finished MP3 to the requesting Discord channel. No hosted
relay, public IP, port forwarding, tunnel or Interactions Endpoint URL is needed.
Discord receives command text and the generated audio; inference and voice
references stay local.

## Setup

1. Create a dedicated application at <https://discord.com/developers/applications>.
   Open **Bot**, generate/reset its bot token, and copy it. Do not use a personal
   account token. Do not share this bot/token between separate running installs.
2. In Discord settings, enable **Advanced → Developer Mode**. Right-click your
   server and choose **Copy Server ID**. Optionally copy permitted text channel
   IDs in the same way. You need permission to install an app in that server.
3. In PacTTSClone **Configuration → Discord integration**, paste the token, enter
   the server ID and optionally allowed channel IDs, select a ready default voice,
   and enable the integration. Save. Configuration and token storage are available
   before Initial Setup finishes; connection waits for successful host setup.
4. Click **Add bot to configured server** after login supplies the application ID.
   Approve `bot` and `applications.commands`, with View Channel, Send Messages,
   Attach Files and Send Messages in Threads. Administrator is unnecessary.
   The bot detects joining its configured server and registers its commands.
5. Use `/voices` to list ready voices. Use `/tts text:Hello voice:<autocomplete>`
   to choose a voice, or omit `voice` to use the configured default. Every ready
   saved voice is available; saved language/speed/inference settings are inherited.

Leave Message Content, Server Members and Presence privileged intents disabled.
Leave the application's Interactions Endpoint URL empty so interactions arrive
through the local Gateway client. A dedicated application is required because
command synchronization owns this bot's guild command set (`tts` and `voices`).
Only the configured server can use generation. A blank channel allowlist permits
all channels in that server where the command is available; a nonempty list
permits only those exact channel IDs (threads require their own IDs). Discord's
normal command and channel permissions still apply. DMs are unsupported.

## Lifecycle and limits

The setting defaults off. Enabled connections resume when the app starts and host
setup is ready. Keep PacTTSClone running. **Save Discord settings / reconnect**
restarts the connection; **Disconnect Discord** disables it while keeping the token.
**Remove saved bot token** disconnects, disables and removes the credential.
**Cancel all work** disables Discord and cancels its queued/running speech; app
shutdown also closes the Gateway and cancels undelivered generation. Old jobs are
never automatically reposted after restart. Commands may remain visible while the
bot is offline; remove the app from the server to remove its installation.

Gateway session resumption restores the connected indicator without requiring
another login. Cancelling a delivery also cancels unfinished generation, including
when cancellation races with queue submission; shutdown waits for that cleanup.

Commands share the bounded generation queue with Local and Twitch. Text limits,
mandatory filters, optional stricter/custom filters and per-Discord-user-ID
cooldowns run before generation. Repeated interaction IDs are deduplicated in
memory for 15 minutes. Rejected requests and accepted speech appear in local
History with Discord origin and stable user identity. Bot commands cannot change
host settings or prepare/upload voice references. `/voices` does not change the
default voice; choose that in Configuration or override it in `/tts`.

`/tts` is deferred immediately, then returns one MP3 attachment. A request still
waiting/generating after 14 minutes is cancelled before Discord's 15-minute
interaction lifetime expires. Completed audio over Discord's supplied attachment
limit stays in local History with an explanatory reply. Missing upload permission,
connection loss or an expired interaction can prevent delivery; generated files
remain local, and posting is not retried automatically. Discord jobs do not
implicitly enter OBS playback. Voice-channel speaking and automatic forwarding
of Twitch/local output are outside this initial integration.

## Credentials and boundaries

The token lives in `data-dir/credentials/discord.json`, outside SQLite and personal
data imports. Windows uses the existing user-bound DPAPI protection; other systems
use a mode-0600 file (base64 is an encoding, not encryption). The browser password
field is cleared after submission and is never filled with the stored token.
API snapshots contain only `token_saved`; no token, interaction webhook token or
webhook URL is written to job history or logs. SDK errors are replaced with fixed
messages before reaching the UI or command replies.

All `/api/discord` endpoints are host-only, including through an authorized admin
tunnel. Changes also require the existing CSRF token. Shared admin pages hide the
Discord settings and do not poll its credential endpoints. No shared bot token is
bundled in the installer. Reset the token in Discord if it is compromised; deleting
the local copy alone does not revoke it at Discord.

## Implementation references

- Discord install scopes/permissions: <https://docs.discord.com/developers/topics/oauth2>
- Interaction response deadlines: <https://docs.discord.com/developers/interactions/receiving-and-responding>
- discord.py command/defer/followup API: <https://discordpy.readthedocs.io/en/stable/interactions/api.html>

Tests use a simulated Gateway/login and fake synthesis with real MP3 encoding.
They do not establish live Discord consent, permissions, command propagation,
network connectivity or GPU performance. A real bot/server acceptance check is
still needed before claiming live integration success.
