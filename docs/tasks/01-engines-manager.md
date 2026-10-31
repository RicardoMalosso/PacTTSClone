# Task 1 — Engines installation manager

Status: completed and released as v2.1.0.
Release: https://github.com/RicardoMalosso/PacTTSClone/releases/tag/v2.1.0
Order: complete and release this task before Task 2. Never bundle Ming or Kitten inference into this release.

## Deliverable
Add an Engines tab available before setup. List OmniVoice, Ming 3.0 and KittenTTS2; future adapters remain explicitly unavailable until their task ships. No misleading working Install/Activate buttons for unsupported engines.

Each row shows exact model/revision; download bytes; installed bytes; peak additional installation disk space; minimum/recommended VRAM with precision, source and test conditions; system RAM; OS/backend compatibility; languages; cloning; emotion/style/tags; streaming; conversion; singing; license; installation/active/loading state; Install/Uninstall/Activate controls. Unknown requirements say Not verified. Distinguish published estimates from actual measurements. Show data directory, available disk and detected/free VRAM. Count shared assets once.

## Implementation
Create a registry and lifecycle manager around existing verified resumable downloads. Preserve existing OmniVoice installs and setup manifests without downloading again. Share manager with Initial Setup. Track installed state separately from active selection and GPU residency. Only one active speech engine; persist selection. Install never activates implicitly. Host-only mutation endpoints enforce current security conventions.

Pin exact revisions and file allowlists/hashes. Preflight disk including runtime/temp overhead; atomic verified installation; cancellable/resumable transfers; real byte progress; restart recovery; clear errors/retry. Do not reinstall packages on activation. Isolate incompatible engine runtimes as needed.

Require idle generation queue for switching/removal. Unload worker before removal. Block uninstall while in use; display reclaimable bytes and preserve shared dependencies, user references/settings/history/output. Restrict deletion to owned manifest paths and reject symlink/path escape. Removing the only installed engine returns generation to an explicit unavailable state. Preserve CUDA-only speech policy, CPU ASR allowed.

## Acceptance and release gate
API and filesystem tests: cache migration, insufficient disk, resume/cancel/restart, checksum failure, safe deletion/shared dependencies, active/in-use blocking, remote access denial. Chromium: table/buttons/progress/errors, reload persistence, EN/PT and mobile layout. Run full pytest, Ruff, Chromium and Windows/Linux CI plus Windows installer acceptance. Record real inference separately from fake-engine coverage. Update docs/status and release notes/version; publish a new immutable GitHub release with installer/update wheel and verified checksums only after required gates pass. Then mark complete and begin Task 2.
