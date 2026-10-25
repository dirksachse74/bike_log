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
- ✅ Groupset import with a template for Shimano Ultegra Di2 R8100 (docs/groupsets.md).
- ⏳ Check the R8100 template against productinfo.shimano.com, then mark it verified.
- 💡 More groupset templates (e.g. Dura-Ace R9200, 105 Di2 R7100, SRAM AXS); optional prices per part.

## P6b Costs and journal
- ✅ Prices on parts (add, edit, replace, groupset import), service cost on maintenance, bike purchase price.
- ✅ Initial and running cost per bike (bike list and bike page, with cost entries and cost per km).
- ✅ Journal with notes and issues on bikes and parts, maintenance notes included.
- 💡 Costs report across bikes per year; editing product reference prices in the UI (API exists).

## P6c JSON product import
- ✅ Templates per part type, importer (app + command line), instructions for script authors/AI agents.

## P7 Imports and Strava
- ✅ CSV import (generic + Strava export), resumable, start date, corrections and exclusions kept.
- 🟡 Strava: `--strava-connect` / `--strava-sync` commands done and tested against a fake Strava;
  first live run on Dirk's machine pending (docs/strava.md).
- ⏳ Confirm the Strava API terms from the full text.

## P8 Packaging and verification
- ✅ PyInstaller spec; Linux frozen build launches, persists, upgrades.
- 🟡 Windows build + installer compiled on Dirk's PC (2026-10-25); install/launch checklist and a clean-machine test pending.
- ⏳ Optional: activate packaging/ci/windows-build.yml.example (needs Dirk's OK).
- 💡 App icon (.ico from the logo), code signing.
