# Default release procedure

## Routine application releases

1. Bump the version in `pyproject.toml` and `src/pacttsclone/__init__.py` together. Run `python scripts/release-identity.py` to confirm the tag. For example, package version `2.3.0rc8` produces tag `v2.3.0-rc.8`. Check that the tag and release are unused.
2. Add release notes in `docs/release-<version>.md`, using the tag version without the leading `v`.
3. Open a PR from a branch in this repository into `main`. Wait for the normal PR checks to pass. Add the `publish-release` label **before merging**.
4. Merge the PR and monitor [Publish validated release](https://github.com/RicardoMalosso/PacTTSClone/actions/workflows/release-merged.yml). The application job runs Ruff and updater tests, builds the wheel and checksums, then verifies the uploaded asset sizes and SHA-256 digests before publishing.
5. Confirm the release is public and contains the canonical app wheel and `SHA256SUMS.txt`. Stable versions become GitHub Latest. RCs publish as prereleases and appear in the updater for users who enable experimental builds.

The routine path skips the Windows installer build and acceptance suite. Existing users can check **Configuration → Application updates**, then restart to apply the downloaded version.

## Windows installer releases

Add both `publish-release` and `installer-acceptance` before merging when a change requires rebuilding the installer, launcher, bundled tools, or base runtime. This path runs full Windows acceptance, including install, launch, reinstall, and uninstall. Confirm the public release contains the setup executable and FFmpeg provenance alongside the wheel and checksums.

New users can reuse the most recent Windows installer that includes the first-launch update check, introduced in RC7. On a fresh installation, setup checks for a newer app before first launch and falls back to its bundled version if the check fails. See [Application updates](auto-updates.md) for compatibility and recovery details.
