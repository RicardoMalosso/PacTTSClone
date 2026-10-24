PacTTSClone 0.3.0-rc.4 fixes installer failure navigation and makes the selected
destination the single root folder.

If you select `foo/PacTTSClone`, application/runtime files go in `app`, data/models/
voices/audio go in `data`, and launch/uninstall shortcuts live at the selected root.
A separate data path is still optional; existing custom paths are preserved rather
than silently moved or deleted. Uninstall removes the private app directory and
shortcuts, retaining data.

Installer failure fix: the introductory timer no longer overrides navigation
buttons on other pages. Preparation errors explicitly do not require a restart,
block Next/Finish advancement, and expose an Open setup log button. Early failures
without a dependency transcript get a fallback setup-error.log at the install root.

The preview is unsigned. Includes the Report a bug video tab and local autoqueue
checkbox from RC3, default voices and previous streamer/OBS features. Dependency
installation is split: native setup installs only private Python, web packages and
project-built FFmpeg. CPU/CUDA inference packages and verified model downloads now
run in the mandatory Initial Setup web tab. Other tabs and generation remain locked
until verification succeeds. Real file byte progress, cache reuse/resume, cancel,
retry and downloadable logs are available. Generation uses local offline paths.

FFmpeg binaries are built in CI from a pinned official source commit, using signed
MSYS2 toolchain/LAME packages; no Gyan FFmpeg build is downloaded. The accompanying
FFmpeg-source-build.zip includes sources, licenses and build provenance.

Windows acceptance covers real wizard/failure handling and minimal installation and real web CPU/model setup,
shortcut launch, repeat setup and data-preserving uninstall. GPU installation and
generation need physical hardware validation; model quality is not inferred from
installation tests.

OBS and separate control links open in new tabs and remain stable during polling.
The generation monitor follows the active local/Twitch/preparation job, restores
on reload and includes a source/stage/timer/cancel strip visible across tabs.
Monitoring Twitch generation does not autoplay its result in the admin browser.

Tunnel controls moved to Configuration. Generate uses saved voices; reference MP3
imports live in Voices. Twitch & OBS now has per-channel connect/disconnect/delete
controls, and General playback is named Local OBS Sources (same URLs). Long MP3
references are automatically cropped to 30 seconds with a persistent notice.
Existing voice thumbnails can be replaced; the four defaults include the supplied
small thumbnails and preserve user customizations on upgrade.

Remote admin tabs/history/media are accessible after host readiness verification;
remote clients avoid owner-only APIs. Scoped OBS links, bounded cookie recovery and
revoked-link polling stop address cross-machine playback failures. Generate now
records a saved requester name, browser UUID and server-derived origin ID. Request
history includes preparation and blocked Twitch commands. Added a fixed status bar,
shared-model warm/cold availability, and title-adjacent language controls.
