# Tasks (prioritised)

Status key: ✅ done and tested · 🟡 done, not verified where it matters · ⏳ pending · 💡 later

## P1 Launch and persistence
- ✅ Single launcher on 127.0.0.1, single instance, data folder outside install folder.
- ✅ Migrations at start with pre-upgrade backup; refuses a newer database.
- ✅ Persistence across restart (dev run and frozen Linux build), real 0002→0003 upgrade.
- ⏳ Same checks on Windows (see packaging/README.md checklist).

## P2 Bikes, components, installations
- ✅ Products vs physical components; install/remove/replace/reinstall with effective dates.
- ✅ Conflicting installations refused (service and database triggers); lifetime usage kept.
- ✅ Replacement workflow with removed-item outcomes, move/swap positions, undo per work session.

## P3 Rides and usage
- ✅ Manual rides add/edit/exclude/restore, exactly-once totals, starting mileage, flags, ledger.
- 💡 Possible-duplicate merge helper (today: flagged only).

## P4 Maintenance rules and reminders
- ✅ Interval and cycle-window rules, explanations, snooze, component overrides.

## P5 Chain rotation and brakes
- ✅ Hot wax / liquid wax cycle, spare chain readiness, independent brake circuits, bleed vs fluid.

## P6 Spare parts (Dirk's first scope)
- ✅ Stock counts per product, individual used-part tracking, replacement integration, low-stock list.
- ✅ Purchases, returns, stock corrections, packages vs units, compatibility verified/unverified.
- ⏳ Edit stock line details in the UI (location, minimum) – API exists (PATCH /api/consumables/{id}).
- ⏳ Compatibility editing in the UI – API exists (POST /api/products/{id}/compatibility).
- 💡 Barcode scanning, automatic ordering (explicitly deferred).

## P7 Imports and Strava
- ✅ CSV import (generic + Strava export), resumable, start date, corrections and exclusions kept.
- ⏳ Strava: small command for OAuth + sync around the tested connector, then a first live run on
  Dirk's machine (needs reset client secret, strava.env, BIKELOG_ENABLE_STRAVA=1).
- ⏳ Confirm the Strava API terms from the full text.

## P8 Packaging and verification
- ✅ PyInstaller spec; Linux frozen build launches, persists, upgrades.
- ⏳ Windows build + installer (packaging/bikelog.iss) + checklist on a clean Windows machine.
- ⏳ Optional: activate packaging/ci/windows-build.yml.example (needs Dirk's OK).
- 💡 App icon (.ico from the logo), code signing.
