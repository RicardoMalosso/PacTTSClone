# Windows bootstrap installer — RC4

User-authorized scope: unsigned small Windows x64 setup and a draft prerelease.
No public publishing, signing purchase, global Python/PATH change or driver install.

The destination is a root containing app/ (private runtime/environments/launcher),
data/ (default models, voices, recordings, caches, settings, logs), and root launch
and uninstall shortcuts. A checkbox unlocks a separate data path. Existing custom
paths are retained. App and data must not overlap. Uninstall retains user data.
Small red bold labels show planning estimates, not guaranteed download sizes.
The first page uses large red instructions and a five-second monotonic Next delay.

Native setup bundles the application wheel and a minimal SHA-256-verified gyan.dev FFmpeg Essentials,
then downloads SHA-256-pinned uv, managed Python and base web packages only. No
PyTorch, CUDA runtime or weights are installed here. Large caches/temp paths are
redirected to data. Windows/Inno may use small system-drive temporary files.
A web-runtime/MP3 smoke must pass before active.json is atomically activated.
Launcher reads that manifest, sets private cache/PATH and opens the local web UI.
The app's mandatory Initial Setup handles inference dependencies and models:
see [web setup design](web-setup-design.md).

FFmpeg is compiled from official FFmpeg/FFmpeg commit
8ae0b34901ba60a802f183ee75a250a9fc3e09a5. MSYS2 supplies signature-verified
compiler and LAME packages. We do not claim upstream distributes our binaries.
Release source archive/provenance/licenses accompany the small bundled tools;
see installer/build-ffmpeg.sh. No Gyan/BtbN precompiled FFmpeg is downloaded.

The timer must only touch Next on the intro page. Preparation failure sets
NeedsRestart=False, disables Next/Finish, exposes Open setup log, and offers retry
or Cancel. Early failures get root/setup-error.log. Native restart requests are
disabled. Tests additionally pass /NORESTART; no real reboot is attempted.

CI compiles FFmpeg and Inno, enforces <10 MiB setup, exercises wizard delay/folder
checkbox/failure behavior, installs to paths with spaces, confirms torch is absent,
launches the actual root shortcut, performs CPU/model setup through HTTP, repeats
native setup and uninstalls while preserving data. Physical GPU validation remains
separate. Draft release creation is gated on those checks. Cache semantics and
future updater scope are documented in README; no auto-updater is implemented.
