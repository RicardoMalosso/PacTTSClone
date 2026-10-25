# RC6 completion report — 2026-10-25

[Published RC6 prerelease](https://github.com/RicardoMalosso/PacTTSClone/releases/tag/v0.3.0-rc.6)
contains the Windows installer, application wheel, FFmpeg provenance and checksums.
It is published (`draft=false`), remains a prerelease, and preserves earlier releases.
Accepted source: `5293b9ab7b6c242b2d6dd4611479eadcaa900172`.

## Delivered

- Per-channel anonymous IRC or authorized OAuth/EventSub. OAuth supports message
  commands, Channel Points, Bits/Power-ups, subscriptions/gifts/resub messages,
  subscription endings, follows, incoming raids and stream online/offline rules.
- Host-only public-client device authorization, Windows DPAPI, refresh/validation,
  diagnostics, duplicate suppression, reward creation/listing, fulfillment after
  OBS playback, failure refunds and missed-redemption recovery.
- Optional Configuration imports, available before setup readiness: model weights
  separately from configuration, voices/transcripts and completed audio/history.
  Model reuse requires exact pinned size/SHA-256; explicit moves preserve unrelated
  files. Personal-data copies preserve the source, back up metadata, remap IDs and
  avoid overwriting current assets or replaying old queues.
- Fixed late initialization resetting an unsaved channel mode, with an old-code
  failing regression. EventSub handoff now drains old-socket notifications while
  the replacement opens. Source-control ignores protect local OAuth credentials.

## Confirmed validation

| Check | Result |
|---|---|
| Final local core suite | 178 passed |
| Chromium suite | 30 passed |
| Ruff, compilation, JS syntax and wheel | Passed |
| Windows/Linux Python 3.11/3.12 | Passed |
| Actual Windows DPAPI roundtrip | Passed in Windows core tests |
| Windows installer acceptance | Passed |
| Real CPU dependencies/model setup | Imports/tools passed; 4,238,811,339 model bytes verified |
| Launcher, reinstall, data-preserving uninstall | Passed |
| Independent build integrity | Artifact ZIP and all four release asset digests/sizes verified |
| Packaged application | 42 files match source after Windows text EOL normalization; binaries exact |
| Production import threshold smoke | Actual 64 MiB fixture scanned/copied/hashed/moved; old config retained |

[Final PR checks](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40163287442)
· [Post-merge checks](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40163520377)
· [Installer acceptance and publication](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40163520519).

The first release gate caught the initialization race and stopped before building
or publishing. The corrected source passed the complete gate; no failed check was
bypassed. The accepted merge tree matches the tested source exactly.

Installer: `PacTTSClone-Setup-0.3.0-rc.6.exe`, 59,754,609 bytes, unsigned.
SHA-256: `cfb975b5b21bd23344a9c829268e996d2039702596b8b6230021967819dc3aa1`.
Original jingling-keys WebM remains bundled byte-for-byte and its digest passed.

## First use and remaining external validation

OAuth requires a registered **public Twitch Client ID** and consent from each
matching broadcaster; none is bundled. [Twitch setup](twitch-eventsub.md) describes
permissions and event rules. [Optional imports](optional-imports.md) describes old
folder selection, copy/move behavior and conflict handling.

Twitch responses and inference in application regressions are simulated. Live
broadcaster consent/paid transactions, physical GPU performance, OBS CEF and physical
hotkey/speaker checks remain separate; the installer acceptance does not claim real
speech quality. One upstream Starlette TestClient/httpx deprecation warning remains.
