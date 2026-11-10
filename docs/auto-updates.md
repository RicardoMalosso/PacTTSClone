# Application updates

Managed Windows installations check public GitHub releases at startup and every six
hours. A verified compatible application wheel downloads automatically. Close and
reopen the app to activate it. Source installs use Git.

Configuration → Application updates offers an experimental RC checkbox (on by
default) and a previous-version selector. Latest follows publication time, newest
first, including RCs when enabled. Selecting a specific version pins it until
Latest is selected again. Compatible in-place rollback starts at 2.1.0, which
introduced persistent engine selection. Older apps may lack newer engines.

The catalogue rejects drafts, ambiguous tags, missing or duplicate canonical wheel
assets, missing SHA-256 digests, unexpected URLs and oversized downloads. It checks
the actual download length/hash, archive paths, identity and installed dependency
compatibility, then smoke-imports the application before atomic next-launch
activation. Failed updates leave the activation pointer in place and show an error.
Dependencies, drivers and model weights are not upgraded by this mechanism.

Preferences live in app-root/updates/preferences.json independently of application
overlays. A content-addressed updater controller and import hook preserve channel
and version controls across rollback. No application is imported by that hook until
normal app startup. Legacy stored voice defaults ignore newer optional fields on
read; HTTP validation remains unchanged. Unsupported active engines are deactivated
on rollback. No data/models are deleted. Each controller behavior change must bump
CONTROL_VERSION, so a newer staged controller replaces an older running controller.

app-root/updates/rollback.pth identifies the previously running application. To
recover manually, stop the app and restore that file as the managed Python
site-packages/pacttsclone_update.pth; removing that pointer restores the base
installed wheel. Reinstall with the same data directory for dependency repair.
PACTTS_DISABLE_UPDATES=1 disables background checks for isolated acceptance tests.

The 2.2.1 stable patch is discoverable by existing stable updaters. A one-time
2.3.0-rc.2 wheel bridges existing 2.3.0-rc.1 numeric updaters. Releases bearing
`<!-- pactts-update-bridge -->` are excluded from the new normal catalogue. Older published assets
are immutable. GitHub controls its native release-history ordering; the app sorts
its own list by published_at.

## App releases and installer releases

A merged release PR labeled `publish-release` publishes the verified app wheel and
checksums. The normal PR checks still apply. The publishing job runs lint and updater
tests, builds the wheel, and verifies the uploaded asset sizes and SHA-256 digests.
A stable app release can be GitHub Latest without carrying a setup executable.

Add `installer-acceptance` as well when the launcher, installer, bundled tools or
required base runtime must change. That path builds the setup executable and runs
full Windows acceptance. The first release of this change needs both labels to ship
the updated setup executable. Thereafter, a fresh install from that executable
uses the existing updater to stage a newer wheel before the first app launch.
Offline installs and failed checks fall back to the bundled wheel. Previously
published executables still check for updates once the app starts and activate them
on the next launch.

Controls and endpoints are local-only, including shared administrators; writes
require the existing same-origin CSRF token. The updater does not run inference,
post messages or send telemetry.

## Stable maintenance release 2.2.2

2.2.2 packages dashboard SSE and native frontend modules as a stable patch release.
Its wheel uses the canonical name pacttsclone-2.2.2-py3-none-any.whl and an uploaded
SHA-256 digest. Latest selects this newer publication for both stable-only and
experimental-enabled channels. A pinned version remains pinned. Existing
2.3.0-rc.1 numeric updaters first take the published 2.3.0-rc.2 bridge, then the new
publication-date controller selects 2.2.2. No second bridge is required.
