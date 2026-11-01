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
`<!-- pactts-update-bridge -->` are excluded from the new normal catalogue. The
normal installer and GitHub Latest designation remain 2.2.1. Older published assets
are immutable. GitHub controls its native release-history ordering; the app sorts
its own list by published_at and uses /releases/latest for the installer link.

Controls and endpoints are local-only, including shared administrators; writes
require the existing same-origin CSRF token. The updater does not run inference,
post messages or send telemetry.
