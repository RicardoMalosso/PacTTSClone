# Known issues and release review — 2026-10-25

Reviewed the earlier pending-features/bugs discussion against the current main
implementation at `e71b39bf8caaf7d4c01466c69da5df3ecf481551`, tests, release assets
and actual GitHub Actions job logs. Historical checkpoints in status.md describe
what was pending at that time; this review records the current outcome.

## Previously reported regressions

| Item | Current result and evidence |
|---|---|
| Remote voices, history and generated MP3 missing | Implemented host readiness and shared result/history/media access. API tests and independent Chromium contexts cover remote administration and scoped media. |
| Remote OBS player 403 loop | Complete scoped links bootstrap cookies; bounded recovery and revoked-link stop are covered by browser/API tests. A bare player URL intentionally grants no remote access. |
| Repeated successful polling logs | PollingAccessFilter suppresses successful state/resource/setup/session/tunnel/tick access logs and retains errors and generation requests; regression covers both. |
| OBS/control links and polling click race | Links open new tabs and remain stable across polling; actual popup navigation is covered by Chromium. |
| Warm/cold state after voice changes | Residency comes from the shared worker; ready voices share that model. Preparation is reference transcription, not training. Engine and worker-reset tests cover residency. |
| Broken automatic reference transcription | Adapter passes decoded float32 PCM to OmniVoice; real MP3/WAV decoding regression prevents a second FFmpeg invocation. Windows FFmpeg smoke covers its float32 protocol. ASR model calls are mocked in the adapter test. |
| Installer failure navigation / unexpected restart | Windows wizard acceptance covers failure state, disabled Next/Finish and logs. Real CPU setup, model verification, launcher, reinstall and data-preserving uninstall passed. |
| Wrong jingling-keys clip / removed sound / no loop | Exact 136,654-byte original WebM is bundled. Real Chromium observes two loops and decoded unmuted audio; closing pauses/resets it. FFmpeg decodes both streams. No Tenor/GIF dependency remains. |
| Validated installer absent from releases | RC5 draft release 423040763 contains installer, wheel, FFmpeg provenance and SHA256SUMS. Main installation instructions now point to RC5. |

No unresolved critical regression was reproduced in this review. This is bounded
by the automated and source-level checks below, not a claim that no bugs exist.

## Remaining feature work

- Deterministic punctuation pauses/prosody are not implemented. Text punctuation
  is forwarded unchanged to OmniVoice; the model does not guarantee pause lengths.
  This remains the explicitly deferred feature in decisions.md, not a completed fix.
- An automatic updater is not implemented. Upgrades use a newer installer with the
  same data directory. Authentication to private releases and rollback need design.
- The RC5 installer uses anonymous IRC. RC6 source adds OAuth/EventSub for Bits,
  points and subscriptions; see [setup and acceptance limits](twitch-eventsub.md).
  Live broadcaster consent/paid-event acceptance remains separate.

These features were not added to or represented as part of the validated RC5
installer during the bug/release review.

## Validation still requiring the target environment

- Public Cloudflare routing and live Twitch connectivity, beyond local simulated
  tunnel requests and deterministic IRC socket tests.
- OBS CEF playback, physical Windows global shortcut delivery, and actual speaker
  output. Chromium audio decoding/state is a separate check.
- Physical NVIDIA/CUDA setup and synthesis on the user's GTX 1660 SUPER, including
  VRAM/latency and perceptual voice quality.

## Confirmed release evidence

- [RC5 installer acceptance](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40140472214):
  full test suite plus Windows setup passed. Logs confirm actual CPU dependencies,
  runtime imports, 4,238,811,339 verified model bytes, launcher, reinstall and
  data-preserving uninstall. No new model synthesis quality claim is inferred.
- [Post-merge tests](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40141216784):
  all seven jobs passed, including Windows/Linux Python 3.11/3.12 and Chromium.
- [Draft promotion](https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40142777679)
  succeeded. The draft remains unpublished and prior release assets are retained.
- Downloaded accepted artifact 12578956283 again during this review. ZIP SHA-256
  `ee019ccdaf14322ba751d1ff3ad0b5af06630e89f1d6c25038d768ab1c8dd697`
  and every SHA256SUMS entry passed. The installer/wheel/provenance digests match
  the draft release asset digests.
- Installer: `PacTTSClone-Setup-0.3.0-rc.5.exe`, 59,725,257 bytes, SHA-256
  `ff3305d4193fc602ab34f1c06ac0c5354fc705aa7de3d3f26cdeda5af3938528`.
- Accepted wheel contains the exact original WebM, SHA-256
  `01f5003f1ad001452249af8939afdecd6cb7470d29772af7d18d038c41d3c894`.

Local rerun results are recorded in status.md. No installer rebuild was necessary
for documentation corrections. The discarded temporary demonstration is excluded.
