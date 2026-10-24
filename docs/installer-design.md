# Windows bootstrap installer — v0.3.0-rc.1

User-authorized scope: unsigned, small Windows x64 setup executable. Download large
dependencies during setup; no preinstalled Python, FFmpeg, Git or admin privileges.
No signing application, purchase, repository visibility change or public publishing.
Prepare a draft prerelease only after Windows build/install tests pass.

## Layout and lifecycle

Inno Setup bundles only the application wheel, bootstrap/launcher scripts and a
pinned dependency manifest. uv downloads a managed Python 3.12 runtime and installs
packages into a version/device-specific venv. Do not modify global Python or PATH.
Choose separate, non-overlapping application and data directories. Redirect uv,
Hugging Face, pip and temporary paths to the selected data directory. The small
Inno executable itself may use Windows TEMP; large downloads must not.

Default device: Automatic, detect NVIDIA through nvidia-smi; explicit CPU/CUDA
available. CUDA selection must pass a torch CUDA check; never silently switch to
CPU after a failed CUDA install. Existing UI hardware settings remain authoritative.
Install CPU and CUDA torch/torchaudio from their corresponding official indexes.
Use a runtime import/FFmpeg smoke before atomically changing active.json. Re-running
setup reuses verified archives and uv cache. Earlier environments are retained for
upgrade recovery until uninstall; failed staging must not replace the active env.

## Downloads and feedback

Pin uv and FFmpeg URLs and SHA-256 digests from official GitHub release metadata.
Reject invalid caches and partial downloads. Python distributions are downloaded
and verified by pinned uv; package hashes are verified by uv/index metadata. This
is not a fully locked transitive environment. uv/FFmpeg archives use explicit
byte-progress output; Python/packages show their actual installer output and step
labels, not an invented aggregate ETA. Errors leave a setup log and a retry path.
Models remain first-use Hugging Face downloads and are not inside the installer.
No automatic sharing/chat connection or model generation during setup.

## Upgrade, uninstall and validation

Launcher reads active.json, sets local caches/PATH, and starts the normal CLI.
Shortcuts preserve a visible terminal for startup errors/Ctrl+C. Uninstall removes
only app-owned runtime/environment directories and installed payload; retains the
separate data directory, including voices, MP3s, settings, models and logs.

CI must compile Inno Setup; enforce <10 MiB bootstrap size; perform a real silent
CPU installation to paths with spaces, validate managed-runtime imports/API/FFmpeg,
repeat setup and preserve a data marker, uninstall and preserve that marker.
GPU install/runtime and interactive wizard on a physical Windows PC remain separate
acceptance checks. Publish unsigned artifacts/checksums to a draft GitHub prerelease
only after those tests pass. Private repository release access stays private.
