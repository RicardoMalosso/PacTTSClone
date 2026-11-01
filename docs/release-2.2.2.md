# PacTTSClone 2.2.2 — dashboard maintenance

- Live dashboard status and generation progress now use one SSE connection, with
  automatic reconnect, state resynchronization and slower REST polling fallback.
- The frontend is split into native vanilla JavaScript feature modules, making
  voices, Twitch, engines, monitoring and configuration easier to maintain.
- Preserves the existing REST API, OBS playback/leases, Discord webhook output,
  saved voices, settings, model caches and generated audio.

This is the stable maintenance patch after 2.2.1. It includes both merged PR #26
(SSE) and PR #27 (frontend modules). No new model download or dependency upgrade
is required by these changes. Direct LAN hosting remains planned.

Managed Windows installations set to **Latest** automatically download the
compatible application wheel at startup or the next six-hour check. Close and
reopen the app once the update is ready. Configuration → Application updates →
Check for updates can request a check now. Installations pinned to a specific
version keep that choice until Latest is selected again.

The update catalogue follows publication date, so the 2.3.0-rc.2 migration bridge
can move to this newer stable publication. A 2.3.0-rc.1 installation first receives
that existing bridge. New installations can use PacTTSClone-Setup-2.2.2.exe.

Validation of the frontend changes: 308 backend tests and all 47 Chromium tests
passed, including SSE reconnection/fallback and native-module control-page/reload
coverage. Publication is additionally gated by the complete GitHub test suite,
Windows installer/update acceptance and uploaded asset size/SHA-256 verification.
Installer is unsigned. These checks do not establish physical GPU synthesis
quality or live Twitch/Discord/Cloudflare connectivity.
