# Task 2 — Ming 3.0 engine

Status: implementation complete; validation/release in progress. Owner requested starting
implementation before Task 1 publication. Task 1 has merged; its separate release is running.
Owner authorized implementation and a separate release.

## Resolve upstream identity first
Verify the exact official Ming 3.0 repository/model variant and current upstream installation/inference API. Record source URLs, revision, license, language/cloning support, supported controls, sample constraints, Windows/CUDA/Python compatibility, model/runtime disk footprint, and documented versus measured RAM/VRAM. Do not substitute another Ming version or invent minimum requirements. If the requested version cannot be verified, record the blocker before offering a replacement.

## Deliverable
Implement a real Ming adapter and pinned runtime using Task 1 registry/install manager. Enable its Install/Uninstall/Activate controls only when functional. Normalize waveform/sample rate into the existing MP3 pipeline. Keep inference in cancellable spawned processes and GPU-only; handle OOM without CPU fallback. Load/unload safely with rollback on activation failure and persist active selection.

Keep original voice references reusable where supported, separate engine-specific preparation caches/settings. Expose only genuinely supported controls with EN/PT hints; reject incompatible parameters. Preserve OmniVoice defaults. Local and Twitch jobs use selected engine; OBS/Discord continue consuming generated MP3s. Store engine/revision/effective settings in history/reports. Define request engine semantics explicitly, requiring idle queues for switching in initial implementation.

## Acceptance and release gate
Adapter argument and lifecycle tests, unsupported-setting validation, cancellation/OOM/recovery, active selection persistence, queue/integration regressions; Chromium install/activate/generate/uninstall and language/settings flows. Real CUDA smoke on supported hardware with valid MP3, recorded model revision, latency and peak VRAM; report quality separately. Run full pytest/Ruff/Chromium and Windows/Linux/installer acceptance. Document hardware limitations honestly; do not call simulated inference a real test. Update docs/status/version and publish a separate immutable release with verified installer/update assets after gates pass. Then begin Task 3.
