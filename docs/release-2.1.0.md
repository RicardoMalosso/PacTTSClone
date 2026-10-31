# PacTTSClone 2.1.0

Adds the Engines tab with OmniVoice install/cancel, explicit activation/deactivation, cache reuse and protected uninstall. Shows pinned model revisions and model byte counts, capabilities, runtime/license information and upstream links. Unknown hardware and installation estimates are labelled unverified.

Generation queues must be idle before engine changes. Saved voices, references, completed audio and history are retained. Engine management is local-only. Ming 3.0 and KittenTTS2 appear as planned integrations; neither is installable in this release.

Validation: 242 local core tests and 39 Chromium tests passed on the implementation. Windows/Linux Python 3.11/3.12, Chromium and actual Windows installer acceptance passed in Actions run 41230207532. Publication additionally runs the gated release workflow for this version. No new GPU quality/performance claim.
