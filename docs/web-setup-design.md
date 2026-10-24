# RC4 setup correction and browser dependency setup

The installation root owns app/ and default data/. Native setup must never advance
past failed preparation or request a reboot. Only the intro page controls its
five-second Next delay; failures expose logs and explicit Back/Cancel behavior.

Installer prepares managed Python, base web dependencies and source-built FFmpeg.
No PyTorch, CUDA or inference extra is installed there. First-run web setup lets the
local owner choose CPU/NVIDIA, explicitly install inference dependencies, cancel,
retry and view logs. Package phases without byte totals remain indeterminate.
Initial Setup is mandatory before other tabs, voice preparation or generation.
The fixed model IDs are resolved to immutable Hugging Face revisions. Download
repository JSON/tokenizer/safetensors assets with actual per-file byte progress.
Hash every reused file (LFS SHA-256; Git blob SHA-1 for ordinary repository files),
reuse exact HF snapshot files, and resume .partial files with HTTP Range. If Range
is ignored, restart that file safely. Never activate files with an invalid hash.
Save manifests and pinned plans under data/models, status under data/setup and logs
under data/logs. Retries show verification versus download and reused-file counts.
After success replace worker model IDs with local directories and offline=True so
preparing voices cannot initiate another hidden model download. Startup checks
presence/size; a rerun performs full hashes. Interrupted setup stays locked and
retryable. Other tabs are disabled in the browser, generation is also guarded on
the server, and saved Twitch channels do not connect until setup is ready.

Run package installation in a cancellable child process. Stop the inference worker
and require an idle generation queue. Lock generation submission while setup is
running. The web process never imports PyTorch; constrain already loaded base
packages to their current versions to avoid replacing in-use native libraries.
Verification runs in a fresh child; no automatic CPU fallback after failed CUDA
verification. Keep uv/package caches under data and write setup logs there.

Setup API is local-owner-only, including when the application is tunneled. No
arbitrary command/package/path arguments come from the browser. Expose CPU/CUDA
choices only, pinned inference versions and fixed official package indexes. A
successful setup verifies imports/device and updates device config; interrupted
setup is retryable and generation remains unavailable until verification succeeds.

FFmpeg: remove Gyan URLs and build a minimal MP3/WAV toolchain from a pinned commit
in official FFmpeg/FFmpeg. CI supplies the compiler and signed MSYS2 LAME package;
record toolchain package versions and hashes. The resulting project-built tools
are small enough to bundle, avoiding unauthenticated downloads from private release
assets. They are not labeled official upstream Windows binaries. Release includes
build recipe/provenance/source references and licenses. No unsigned builder's
precompiled FFmpeg is fetched by setup.

## RC5 live setup progress

Live updates are exposed via local SSE at `/api/setup/stream` and backed by the normal
`/api/setup` snapshot. Initial model downloads use actual byte reports; dependency
wheels use `pip --progress-bar raw` through a pipe, reporting each package's
actual bytes and percent only when the server declares a total. Download speed
and ETA are measured over the last emitted interval, not a promise.
Timestamped stdout/stderr is persisted to runtime-setup.log and the UI shows
its most recent 500 lines in an always-open scrollable panel. Browser refresh
and server restart can restore the tail of this log.
The once-only countermeasures offer is claimed server-side by an authenticated
request before displaying the prompt; declined, closed and accepted offers are
all consumed. An independent local WebM video overlay does not pause or cancel setup.
