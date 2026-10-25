# Optional imports from another installation

**Configuration → Import stuff (optional)** is available both before Initial Setup
finishes and afterward. Initial Setup remains mandatory for inference, but it does
not require any import. Voices, chat, history and generation remain gated until
setup verifies the inference runtime and complete model files. Import operations
require the host PC, an idle generation queue and disconnected Twitch channels.
Shared administrators cannot access local paths or import endpoints.

## Models: reproducible downloads

Enter the old installation's `data`, `data/cache`, or specific model-cache folder.
For example, the source can be `G:\Temp_install\PacTTSCLINSTALLFOLDER\data\cache`
while the current installation is `G:\temp_install\someFolder`.
**Find existing model weights** scans known locations plus specified folders;
review candidate paths/sizes, then explicitly click **Import verified model weights**.
No scanning/import action is required for normal setup.

Only safetensors weights of at least 64 MiB are eligible for reuse. Hugging Face
hash-named blobs are recognized. Names and timestamps alone never establish
compatibility: imported bytes must match both size and SHA-256 in the current
setup's pinned model plan. Old JSON/tokenizer/configuration files are not imported.
The import action may fetch official revision metadata; it never downloads missing
weights or small configuration files. Initial Setup fetches anything still missing.

Copy is available by clearing **Move verified weights**. Move applies only to
matching originals inside folders explicitly entered by the user. Each new copy
is streamed, hashed and published atomically; originals are removed only after the
new weight copies verify. A changed/incompatible file is retained. Automatically
found shared caches are copied and preserved. Originals outside selected roots are
never removed. `models/weight-import-receipt.json` records transferred files; an
unremovable source is retained and recorded as a warning. The old installation
may need to redownload moved weights. No configurations, voices or output files
are removed by model import. Normal cache reuse within the current installation
continues independently of this optional transfer.

Discovery is bounded to 30 seconds, 50,000 files, 200 candidates and depth 10 per
search, avoids directory symlinks/environments/recordings and supports cancellation.
Use a more specific folder when a limit is reached. Additional roots must be local
absolute paths; network shares are rejected. Setup/import can also be cancelled.
No broad scan of every drive runs automatically.

## Personal data: configuration, voices and outputs

Point to the previous **data folder** containing `pacttsclone.sqlite3`, `voices`
and `outputs`, or its installation parent containing `data`. A cache-only folder
has no voice/configuration database and cannot supply this category.
Select any of:

- **Channel configuration:** imports new channel definitions with remapped voice
  references; existing channel settings are kept. Imported channels start
  disconnected and playback-paused. Enable **Also replace application settings**
  only to apply the source's CPU/device/queue/hotkey settings explicitly.
- **Saved voices and transcripts:** copies reference MP3s, thumbnails and metadata.
  Imported voices get installation-local IDs; saved transcripts remain ready,
  blank references require preparation. Existing voices are never overwritten.
- **Generated audio and history:** copies completed MP3s and remaps their history
  links, retaining original text/timings when available. Orphan MP3 outputs receive
  an imported-audio history entry. It does not regenerate or autoqueue the audio.

Personal data is always **copied**, preserving the source folder. IDs are stable
for repeat imports from the same source installation, so repeat imports do not
create duplicate voices/audio. The current SQLite database is backed up under
`import-backups` before activation. Files stage and verify first, then new records
are committed in one transaction. Conflicts abort without overwriting assets;
partial new assets are removed on rollback. Cancellation leaves the source intact.
Warnings/counts and the metadata backup path appear in the UI.

SQLite's backup API captures a consistent committed snapshot, including WAL data.
Stop the old application first so its media files are not changing during import.
Source paths escaping the selected folder are rejected. Imported jobs never retain
old workspace paths or replay old pending queues. Models, runtime packages, tunnel
keys, Twitch OAuth credentials, caches and logs are not copied with personal data.
Authorize Twitch accounts again on the destination installation.

Automated tests cover matching/outdated weights, explicit moves, shared-cache
preservation, omission of old configs, personal-data mapping/idempotency, backups,
explicit settings replacement, rollback/cancellation, host-only APIs and browser
access to Configuration/imports before setup readiness. Tests use small weight
fixtures with a lowered threshold; production always uses 64 MiB.
