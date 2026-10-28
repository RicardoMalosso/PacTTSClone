# PacTTSClone RC10

- **Automatic speech language by default:** new and existing voices without a configured language use Automatic, including Twitch chat commands and Twitch events. The legacy upload API also defaults to Automatic.
- **Language in Voices:** save Automatic, Português or English under each voice's generation defaults. Twitch inherits it; Local loads it and allows a one-job override. Restore defaults returns to Automatic.
- **Consistent Local behavior:** previous browser-only language preferences no longer override voice defaults. Interface language remains independent.
- **Distribution:** separate unsigned RC10 Windows installer, application wheel, FFmpeg provenance and SHA-256 checksums. Earlier releases remain untouched.

Publication requires the full Linux/Windows Python 3.11/3.12 suite, Chromium tests, actual Windows wizard/install/reinstall/uninstall acceptance, and uploaded asset integrity checks. Deterministic tests use fake inference and do not establish CUDA performance or speech quality.
