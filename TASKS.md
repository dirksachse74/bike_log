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
- ✅ Add part / Install: "Where does it go?" (spare, bike position, or on a part: wheelset › wheel › hub, crankset › chainring, RD › pulleys); Rim type.
- ✅ Fix button on incidents (replaced from stock/spare/new, patched, nothing yet; auto-solve; Undo fix) and Manage parts → Swap tube; tubes as stock items.
- ✅ Flat tire per wheel: tube only / tube and tire (one incident); spares to keep (2 tubes, 1 tire, editable) on the shopping list; Overview = Upcoming tasks + Shopping list, rest folded.
- ✅ Bike page "Manage parts": Swap chain / wheels or wheelset / tire / another part (shortcuts to Replace), Install a part, Add groupset, Group wheels; a stored wheelset keeps its own wheels on a swap.

## P3 Rides and usage
- ✅ Manual rides add/edit/exclude/restore, exactly-once totals, starting mileage, flags, ledger.
- 💡 Possible-duplicate merge helper (today: flagged only).

## P4 Maintenance rules and reminders
- ✅ Interval and cycle-window rules, explanations, snooze, component overrides.

- ✅ Time-based reminders: brake fluid 24 months, sealant top-up every 3 months for tubeless tires.
- ✅ Tube/tubeless setting on wheels (moves with the wheelset); headset service rule.
- ✅ Ride-hour and number-of-chains rules; charging reminders (Di2, power meter, sensor, coin cells).
- ✅ Ride incidents (flat/crash/defect) linked to ride and part; dry/wet per ride.
- ✅ Incidents reworked (Dirk, 2026-10-26): 13 types with their own affected parts or body areas, several
  per incident, edit / remove / restore on the ride, tidier ride page; Solved / Re-open buttons.
- ✅ Ride page: distance and time summary (ride, bike total, year, month); parts list with hours behind "Show details".
- ✅ Bike page in tabs; "Installed now" grouped and folded; Service status folds what is not due; Rides and Incidents tabs.
- ✅ One row per incident everywhere (fixed columns), "Add incident".
- ✅ Wheelset assemblies (wheels, tires, hub, bearings, spokes, rim tape, sensor), pulley wheels, carry-over.
- ✅ Maintenance coverage review items 1–22 (bike-level rules, measurement limits, torque checks, crash
  inspection, hanger, cleats/shoes, thru-axles, sealant clean-out, valves, Di2 checks, bearings, bar tape,
  hoses, bed-in, worn chain → cassette, wet ride, tire age, stem, cables (mechanical only), chargers).
- ⏳ Editing a bike-level rule for one bike in the UI (API exists: PATCH /api/bikes/{id}/rules/{code}).
- ✅ Review item 23: yearly full service of the whole bike with a tick-box checklist.
- ✅ Review item 24: tire pressure note per tire, shown on the bike page (note only).
- ✅ Assioma pedal charge reminder at 80 ride hours (Dirk, 2026-10-26).
- ✅ Bugs B1–B15 from the imaginary-bike test run (B5 was fixed with the quick-link carry-over).
- ⏳ Bike installation history and a tire's change log could also list the bikes a wheel took its
  mounted parts to (UAT B6 second half; the km table already shows them).
- ✅ Sample database as the first-start default (wiped by Fresh start).

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
- ✅ More groupset templates, 12/13-speed Shimano and SRAM (11 more; all unverified until checked with the makers).
- ⏳ Check the groupset templates against productinfo.shimano.com and SRAM spec sheets.

## P6b Costs and journal
- ✅ Prices on parts (add, edit, replace, groupset import), service cost on maintenance, bike purchase price.
- ✅ Initial and running cost per bike (bike list and bike page, with cost entries and cost per km).
- ✅ Journal with notes and issues on bikes and parts, maintenance notes included.
- ✅ Purchase bundles (groupset at one price, counted once), parts kept as spares at import, grouping existing parts later.
- ✅ Km from before on a part (starting mileage, date defaults to first install).
- ✅ Fresh start (reset database) with a kept backup, and Restore for every backup in Settings.
- 💡 Costs report across bikes per year; editing product reference prices in the UI (API exists).

## P6d History and diagnostics
- ✅ Change log for every bike and part (old → new, when, who), shown on their pages.
- ✅ Settings → Diagnostics: view and download the log, secrets removed.
- 💡 Change log for products (catalogue data) and service-rule edits.

## P6c JSON product import
- ✅ Templates per part type, importer (app + command line), instructions for script authors/AI agents.

## P7 Imports and Strava
- ✅ Rides area: assign/change/remove the bike per ride or in bulk (kept on re-sync), Removed rides with
  restore (never re-imported), disconnect keeps rides, 30-day sync look-back.
- ✅ CSV import (generic + Strava export), resumable, start date, corrections and exclusions kept.
- 🟡 Strava: set up, connect, sync and disconnect from Settings (and command line); tested against a
  fake Strava; first live run on Dirk's machine pending (docs/strava.md).
- ⏳ Confirm the Strava API terms from the full text.

## P8 Packaging and verification
- ✅ PyInstaller spec; Linux frozen build launches, persists, upgrades.
- 🟡 Windows build + installer compiled on Dirk's PC (2026-10-25); install/launch checklist and a clean-machine test pending.
- ⏳ Optional: activate packaging/ci/windows-build.yml.example (needs Dirk's OK).
- 💡 App icon (.ico from the logo), code signing.
