# PacTTSClone 2.2.1 — updater channels and previous versions

Installer installations download compatible application updates automatically at
startup and every six hours. Experimental releases (RC) are now included by default.
Close and reopen the app to activate a staged update.

Configuration → Application updates lets you turn experimental builds off, pin a
previous compatible release, or choose Latest to resume automatic updates. The
version list follows publication date, newest first. Models and personal data are
retained. An older application can lack newer engine support.

Existing stable installations receive this stable patch through their current
updater. Existing 2.3.0-rc.1 installations first receive the update-only
2.3.0-rc.2 compatibility bridge; their old numeric updater cannot select 2.2.1.
The bridge contains these same changes. The new updater then follows publication
date and excludes migration-only releases.

Preserves the 2.1.1 Discord webhook sender/message fix. No new inference engine or
physical GPU validation is introduced by this updater patch.
