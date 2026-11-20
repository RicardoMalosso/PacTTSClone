# PacTTSClone 2.3.1

- **Local volume diagnostic:** Configuration can test a saved voice's volume by
  measuring a clearly labeled calibration tone through the production MP3 encoder.
  It writes no persistent audio and does not run TTS inference.
- The local JSON report compares the configured gain with a 100% baseline and
  includes decoded RMS, peak, duration, file size and checks. It also explains that
  it cannot inspect OBS mixer/filter levels or physical audio output.

This is an application-only update. Existing installations receive it through the
automatic updater; no installer or model download is required.
