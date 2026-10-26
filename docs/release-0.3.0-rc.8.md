# PacTTSClone RC8

Twitch authorization now uses PacTTSClone's bundled public Client ID. Save the channel, click Connect Twitch, and approve the matching broadcaster on Twitch. No client secret, developer registration or key entry is required for users. Existing authorizations are retained.

Report a bug loads the YouTube player on demand, keeps the current tab visible until the player is ready, then opens the report tab and requests playback after 200 ms. Navigation/panic cancels pending playback. Autoplay policy may require a manual click.

Public-client device challenge and secret-free pending polling were verified live against Twitch. Tests simulate broadcaster consent and video readiness, not actual consent or YouTube autoplay policy. Release is gated by Windows/Linux tests, Chromium and real Windows installer acceptance. Existing RC7 features and cached-data reuse remain.
