# PacTTSClone v2.0.0

- **Discord webhooks:** replaces the bot/token integration. Mirror selected newly
  generated local/Twitch MP3s to a Discord channel. Includes a test button,
  source/channel/voice filters, clear errors and step-by-step setup instructions.
  Webhooks are output-only; Discord chat commands are not supported.
- **Automatic updates:** checks public releases at startup and every six hours,
  downloads verified application wheels, and activates them after reopening.
  Models, CUDA packages and personal data remain in place. Includes manual checks
  and rollback support; incompatible runtime dependencies require setup repair.
- **Per-voice output volume:** 0–300%, saved for each voice and overridable for a
  local generation. Applied inside the MP3, including OBS and Discord output.
- **Mouseover help:** English/Portuguese explanations for every generation control.
- Standardized package/release/installer identities and stable release handling.

Install v2 once over the existing installation with the same data directory.
Future compatible application updates do not require the installer. Previous
MP3s keep their existing volume. Legacy Discord bot credentials are removed;
configure a webhook if you want Discord delivery.

The installer remains unsigned. Windows acceptance validates installation,
launcher, CPU dependency/model setup, update activation and rollback, reinstall
cache reuse, and uninstall preserving data. No physical GPU or live Discord
quality/performance claim is made.
