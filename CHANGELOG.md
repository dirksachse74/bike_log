# Changelog

What changed in each Bike Log version. Versions are MAJOR.MINOR.PATCH: PATCH = fixes only, MINOR = new
features, MAJOR = big changes (for example to the data format). A build between releases shows its commit
after a plus sign, e.g. `0.2.0+abc1234` = version 0.2.0 plus later changes. How to make a release:
UPDATING.md → "Making a release". New entries go under "Unreleased" as work is done.

## Unreleased

## 0.2.0 (2026-10-25)

### Added
- Proper versioning: one version number for the app, the screens, BikeLog.exe (Windows file properties)
  and the installer (`BikeLog-0.2.0-setup.exe`); builds between releases carry the commit; this changelog;
  `scripts/release.py` to make a release.
- Settings shows the version, database schema and the commits of the app and the screens; a red bar warns
  when the screens are older than the app or an older copy is still running.
- One-step Windows build script `packaging/build.ps1` that stops at the first error.
- Tube/tubeless setting on wheels (moves with the wheelset), sealant top-up reminder every 3 months for
  tubeless tires, headset service reminder.
- Change log on every bike and part (old → new, when, who).
- Settings → Diagnostics: view and download the log, secrets removed.
- Headset and power meter part types.
- Rides area with tabs Rides / No bike / Removed rides; assign, change or remove the bike per ride or for
  several rides (kept on Strava re-sync); removed rides can be restored and are never imported again.
- Strava set up, connected, synced and disconnected from Settings (no command line).
- JSON product import with one template per part type, and instructions for scraper authors.
- Prices on parts, initial and running cost per bike, journal for bikes and parts.
- Groupset import with a Shimano Ultegra Di2 R8100 template.
- `UPDATING.md`: how to pull and rebuild on Windows.

### Changed
- Disconnecting Strava keeps all rides. Strava sync looks back 30 days so gear changes are picked up.
- Database schema 0003 → 0005 (upgraded automatically with a backup first).

## 0.1.0 (2026-10-25)

First build installed on Windows: bikes, parts and installations, rides and mileage, maintenance rules and
reminders (hot wax, liquid wax, chain wear, brake fluid, pads, wheels), spare parts and replacement with
undo, CSV import (including the Strava export), backups and export, demo mode. Database schema 0003.
Not tagged in git (it was built before versioning).
