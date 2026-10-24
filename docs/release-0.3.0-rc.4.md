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
