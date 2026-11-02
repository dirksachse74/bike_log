# Tasks (prioritised)

Status key: ✅ done and tested · 🟡 done, not verified where it matters · ⏳ pending · 💡 later

## PHP multi-user web version (php/, DECISIONS 139) — full feature match before release

- [x] Base: accounts (sign-up, email confirmation, reset, invitations), admin page, bikes, parts, install
      history and per-part km, rides form, maintenance, reminders, supplies, tests on MySQL (php/tests).
- [x] Round 2: groupset import, wheels/tire setup, spokes, punctures and incidents, spares and counted
      stock, spare minimums and shopping list, frame and fork as one part, notes and issues (journal).
- [x] Round 3a: chain rotation and wax cycle (liquid top-up window, after_top_up_km, wet rides), PARENT_COUNT
      (quick link).
- [x] Round 3b: purchase bundles and costs, repairs (send away), service orders, part life report and
      forecast.
- [ ] Round 4: product records and JSON product import, pick lists (shops), fresh start, per-user backup and
      restore (JSON import), diagnostics and change log, ride times (not only dates), usage profiles.
- [ ] Try it on real shared hosting (Dirk): install page, SMTP, HTTPS.

## P1 Launch and persistence
- ✅ Single launcher on 127.0.0.1, single instance, data folder outside install folder.
- ✅ Migrations at start with pre-upgrade backup; refuses a newer database.
- ✅ Persistence across restart (dev run and frozen Linux build), real 0002→0003 upgrade.
- ⏳ Same checks on Windows (see packaging/README.md checklist).

## P2 Bikes, components, installations
- ✅ Products vs physical components; install/remove/replace/reinstall with effective dates.
- ✅ Conflicting installations refused (service and database triggers); lifetime usage kept.
- ✅ Replacement workflow with removed-item outcomes, move/swap positions, undo per work session.
- ✅ Add part → Groupset opens the groupset dialog (Dirk 2026-11-01).
- ✅ Part life report (Inventory → Part life) and pace forecast on km/hour reminders (G3).
- ✅ Send a part away for repair and record what came back (4 outcomes, cost, receipt, incident, put back on).
- ✅ Frame and fork as one part (Dirk 2026-10-26); automatic forks removed.
- ✅ Frame and fork as parts (km, serial, warranty until, warranty replacement, frame history).
- ✅ Retire or delete a bike (delete only without history; Strava does not re-create it; Retired bikes list; Restore).
- ✅ Manage parts as Add / Remove / Change parts with a Groupset sub-group (change one part, replace whole groupset); Add groupset only on a bike without one; incident buttons on one line.
- ✅ Chain rotation: mark per part, rotation card on the bike (on / waxed, ready / dirty), swap prompt from the 500 km hot-wax rule with one-click swap, Wax chains batch, rotation history, wax cycles per chain (with liquid-wax top-ups; hot wax 200 km after a top-up, DECISIONS 133). Add picker offers chains from other rotations and from stock, "Other chains" says where the rest are (DECISIONS 131).
- ✅ Drill-down: part page "Parts on it" tree (wheelset → wheels → hub/spokes/tire, crankset → chainrings); groupset one line on the bike + groupset page (stats, tasks, incidents, log, journal, parts tree).
- ✅ Spokes per wheel with broken-spoke count, "Broken spoke" incident and fix, re-lace reminder after 3 (Settings).
- ✅ Install a part: create a new part and install it in one step (DECISIONS 112).
- ✅ Cockpit part type; properties (and notes) editable in Add part and on every part page; wheelset rim widths, depth front/rear, tire size range (DECISIONS 111).
- ✅ Di2 wires / junction box are their own part types in the groupset, existing "Other" wires moved (DECISIONS 110).
- ✅ Broken spokes logged on the wheel (broke on / replaced on, history, remove), "Replace the wheel" after the 3rd; spokes dated from the wheel's purchase (DECISIONS 109).
- ✅ Add part / Install: "Where does it go?" (spare, bike position, or on a part: wheelset › wheel › hub, crankset › chainring, RD › pulleys); Rim type.
- ✅ Fix button on incidents (replaced from stock/spare/new, patched, nothing yet; auto-solve; Undo fix) and Manage parts → Swap tube; tubes as stock items.
- ✅ Flat tire per wheel: tube only / tube and tire (one incident); spares to keep (2 tubes, 1 tire, editable) on the shopping list; Overview = Upcoming tasks + Shopping list, rest folded.
- ✅ Bike page "Manage parts": Swap chain / wheels or wheelset / tire / another part (shortcuts to Replace), Install a part, Add groupset, Group wheels; a stored wheelset keeps its own wheels on a swap.

## P3 Rides and usage
- ✅ Manual rides add/edit/exclude/restore, exactly-once totals, starting mileage, flags, ledger.
- ✅ Delete a bike for good (hidden everywhere, backup first); tires/tubes share names, the mark is part of the name "Name [A]" (DECISIONS 132); defect tube flag (DECISIONS 128–130).
- ✅ Wheel page: Tire and inner tube card (current + history with own km, DECISIONS 127).
- ✅ Install an inner tube (spare, from stock, new, used); tubes on recorded wheels count km (DECISIONS 125).
- ✅ Remove / restore several rides at once (tick rides → Remove rides, with km preview; DECISIONS 124).
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
- ✅ Tires: wheelsets always have front and rear wheels; new / used (km) / spare tire; move front→rear and swap (Dirk 2026-11-01).
- ✅ Install a tire from the wheel, wheelset and bike pages; Install on a stored part's page (Dirk 2026-11-01).
- ✅ Shop ("Bought from") dropdown on parts, bikes, stock, bundles and repairs; Settings → Lists to add, rename, merge and hide (Dirk 2026-11-01).
- ✅ A second identical part with the same name gets "(2)" instead of an error (Dirk 2026-11-01).
- ✅ Breadcrumbs on pages below a main menu item, following the way you came (Dirk 2026-11-01).
- ✅ Maintenance log: Edit / Delete / Restore per entry (Dirk 2026-11-01); Add part Save / Cancel back to Inventory.

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
- ✅ Strava: import only rides with known bikes (DECISIONS 119).
- ✅ Ride notes, 2000 characters (DECISIONS 118).
- ✅ Puncture statistics, Rides → Punctures (DECISIONS 117).
- ✅ Bike shop on Record work done (DECISIONS 116).
- ✅ Frame in Costs: Frame line + Frame price; frame price = initial cost when there is no bike purchase price, else included (DECISIONS 113).
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
- ✅ GitHub Releases: .github/workflows/release.yml builds, tests and publishes the installer (2026-11-01).
- ⏳ Decide where friends download from (repo is private): public repo, public releases repo, or send the file.
- 💡 App icon (.ico from the logo), code signing.
- ✅ Settings → Service intervals (all type defaults in one place) and a Charging card with time and km between charges (DECISIONS 134).
