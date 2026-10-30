# Application updates

Managed Windows installations check public GitHub releases at startup and every
six hours. Configuration includes status, errors and a manual check. Downloads
are automatic; activation takes place only after closing and reopening the app.
There is no forced restart during streaming. Source installations use Git.
The first updater-enabled version requires one normal installation.

## Release contract

`pyproject.toml` is the version source: `X.Y.ZrcN` becomes `vX.Y.Z-rc.N`,
`X.Y.Z` becomes `vX.Y.Z`. Runtime version must match. Release identity is derived
and checked in CI, replacing hardcoded RC11 tags. Never replace published assets.
The gated installer workflow continues to require full tests and Windows acceptance.
Each release includes exactly one `pacttsclone-VERSION-py3-none-any.whl` with a
GitHub SHA-256 asset digest. Drafts, malformed tags, missing digests and mismatched
asset URLs are ignored. Stable installs ignore RCs; RC installs accept newer RCs
and stable releases. Numeric version comparison prevents rc9/rc10 ordering errors.

## Apply and recover

The updater downloads only the wheel (bounded to 128 MiB), verifies size and SHA-256,
rejects unsafe archive paths, verifies package identity and installed dependency
compatibility, then imports the staged app in a separate process. It never installs
CUDA, models or dependencies. Incompatible dependency changes report an actionable
error and require runtime repair through normal setup. Automatic dependency
migration is deliberately outside this application-only protocol.

Application files are extracted under `app/updates/VERSION`. An atomic Python
`.pth` file places the verified version ahead of the base package on the next
launch. The running server's import path is unchanged. Failed download, extraction,
dependency or import checks leave the active installation intact. Old versions
are retained. Stop all application instances before reopening to activate.

To roll back, stop the app, find `pacttsclone_update.pth` in the active Python's
`Lib/site-packages`, and replace its contents with `app/updates/rollback.pth`.
Deleting `pacttsclone_update.pth` restores the installer-provided base version.
Models, voices, database and output are untouched; database schema migrations in
future releases must remain backward compatible with the retained base version.
Hashes protect download integrity; trust remains in the GitHub repository and
HTTPS, without a separate publisher signature. No downgrade or forced shutdown.
