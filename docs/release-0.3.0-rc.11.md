# PacTTSClone RC11

- **Discord integration:** configure your own bot token locally under Configuration, restrict access to one server and optional channels, and choose a saved default voice.
- **Slash commands:** `/tts` generates speech on your PC and replies with an MP3; `/voices` lists ready voices. Saved language and generation settings apply.
- **Queue controls:** shared bounded generation queue, filters, per-user cooldowns, duplicate prevention, interaction timeout and cancellation cleanup.
- **Credentials:** host-only settings, Windows DPAPI protection, token removal and no token returned to the browser. No privileged Discord intents or public endpoint required.
- **Reliability:** reconnect status recovers after Gateway resume; cancellation cleans up unfinished generation; failed uploads retain completed audio locally.

Setup guide: [Discord configuration](https://github.com/RicardoMalosso/PacTTSClone/blob/main/docs/discord.md).

The unsigned Windows installer is accompanied by the application wheel, FFmpeg provenance and SHA-256 checksums. Publication requires full Windows/Linux and Chromium tests, actual Windows installer acceptance and uploaded asset verification. Existing releases are preserved.

Automated Discord tests simulate the Gateway/API and inference with real FFmpeg output. Live Discord delivery and physical GPU performance remain unverified. Voice-channel playback is not included.
