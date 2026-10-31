# Task 3 — KittenTTS2 engine

Status: implementation in progress. Tasks 1 and 2 released as v2.1.0 and v2.2.0-rc.1.
See [integration and validation record](../kitten-integration.md).
Owner authorized implementation and a third separate release.

## Resolve upstream identity first
Verify the exact official KittenTTS2 name/version/model variant. Record authoritative repository/model card URLs, pinned revision, license, supported languages/voices/cloning and controls, inference API, Windows/Python/backend compatibility and actual disk/runtime footprint. Separate published RAM/VRAM estimates from measured results. Do not silently substitute KittenTTS or another revision.

## Deliverable
Implement a dedicated engine adapter and installation/runtime manifest using Task 1 infrastructure. Enable Install/Uninstall/Activate once working. Verify GPU execution is actually available: a CPU-only upstream runtime conflicts with current GPU-only speech policy and must be reported rather than silently bypassed. No fabricated CUDA support.

Normalize audio into the existing MP3/output pipeline; support cancellation, unload, activation rollback, persistence and clear failures. If upstream offers preset voices rather than cloning, provide engine-specific voice selection and explain unsupported reference cloning. Store settings/prepared caches per engine; hide unsupported OmniVoice controls and retain their saved values. Update Local/Twitch compatibility validation, history/monitoring and EN/PT hints; preserve OBS/Discord output handling.

## Acceptance and release gate
Test supported voices/parameters, reference compatibility rejection, runtime/activation persistence, cancellation, audio normalization, uninstall safety and regression coverage for OmniVoice/Ming. Chromium covers installation, voice selection, generation/errors and switching. Run real supported-backend smoke with recorded revision/requirements; full pytest, Ruff, Chromium and Windows/Linux plus installer acceptance. Record unresolved hardware limitations explicitly. Update docs/status/version and publish its own immutable release with verified installer/update wheel/checksums after required gates pass.
