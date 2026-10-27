# PacTTSClone RC9

- **Per-voice generation tuning:** save OmniVoice speed, optional duration, inference steps, denoise, CFG, prompt preprocessing and output postprocessing independently for each saved voice. IRC/EventSub requests inherit these defaults; the Local Generate tab may override them for an individual job. Existing voices and checkpoints are retained.
- **Configuration countermeasure button:** open the original bundled jingling-keys WebM with its two-second loading animation. Audio loops until closed; reopening works without affecting Initial Setup.
- **Bug-report guide:** retain the video-ready gate and 200 ms autoplay attempt; show the optional direct YouTube link only two seconds after the tab actually becomes visible.
- **Distribution:** new unsigned Windows installer, application wheel, FFmpeg provenance and SHA-256 checksums. Separate v0.3.0-rc.9 draft; RC8 remains untouched.

Release validation requires passing Python 3.11/3.12 checks on Linux and Windows, Chromium browser tests, interactive Windows installer acceptance (including repeat install and uninstall), and integrity/provenance checks. Automated mocked-inference tests cannot establish NVIDIA CUDA performance or the perceptual quality of generated voices. YouTube autoplay and Twitch user consent depend on external browser/provider behavior.
