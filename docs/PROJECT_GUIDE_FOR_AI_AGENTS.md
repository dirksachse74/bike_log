# Bike Log: project guide for an AI agent taking over

This document is self-contained. Read it first, then `DECISIONS.md` (why things are the way they are),
`TASKS.md` (what is open) and `HANDOVER.md` (what was tested). State as of 2026-10-25, branch
`claude/project-thread-6y3mmh`. It contains no secrets and must never be given any.

---

## 1. What this is

**Bike Log** is a private, local desktop app that tracks the life of road bikes: rides and mileage,
components and their wear, maintenance and service intervals, spare parts and consumables, costs, and a
journal. Owner and only user: Dirk (a data engineer; new to Git, so explain Git steps plainly). His bikes:
BMC Roadmachine, Cannondale Synapse Di2, Cube SL Road SL, Cannondale Synapse HiMod, TIME NXR. Indoor
(Zwift) rides arrive as Strava `VirtualRide`.

It runs on his Windows PC: one program starts a local web server on `127.0.0.1` and opens the browser.
Nothing is hosted or deployed. Data stays in his user folder.

### Product principles (from Dirk's brief; do not break them)

1. **Start with incomplete data.** Every number says whether it is known, estimated (≈) or a minimum (≥).
   Only a part's type and label are required; everything else can be added later.
2. **Quick logging.** Common actions (hot wax, inspection, ride) take a few taps; forms keep input on errors.
3. **Totals are derived, never accumulated.** Mileage per part and running cost per bike are rebuilt from
   records, so repeating or correcting an operation can never double-count.
4. **No hard deletes.** Records are voided/retired with a reason and stay in history (database triggers
   enforce this for history tables). No exceptions: removing a ride moves it to *Removed rides*, and
   disconnecting Strava keeps every ride (Dirk does not want mass deletes).
5. **The core app works without Strava.**
6. **All mileage, reminder, stock and cost logic lives in Python services.** The UI only displays results.
7. **Never claim untested things work.** Say exactly what was tested and where (cloud Linux vs Dirk's Windows).

---

## 2. Stack and architecture

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2.1, Alembic, SQLite (WAL, `BEGIN IMMEDIATE` writes) |
| Frontend | React 19 + TypeScript + Vite, React Router (hash routes `#/...`), plain CSS (`index.css`, light/dark) |
| Packaging | PyInstaller one-folder build (`BikeLog.exe`), optional Inno Setup per-user installer |
| Tests | pytest (backend, against a real SQLite DB, no mocks of our own code), Playwright browser script (`e2e/smoke.cjs`) |

Runtime shape:

- `python -m bikelog` / `BikeLog.exe` = `backend/bikelog/launcher.py`: single-instance lock, data folder,
  migrations (backup first), daily backup, starts uvicorn on 127.0.0.1 (port 8765 or the next free one),
  opens the browser. Command-line flags for backup/export/restore/Strava/JSON import (section 8).
- `backend/bikelog/api/app.py`: all HTTP endpoints under `/api`, serves the built frontend.
- Security (`api/security.py`): only Host `127.0.0.1`/`localhost` (DNS-rebinding guard), every mutation
  needs the per-launch `X-BikeLog-Token` (injected into `index.html`), no CORS.
- Mutating endpoints take `X-Client-Op-Id` so a double click/retry is applied once (`operations.run_once`),
  and many accept `?dry_run=true` to preview the change (`with_change`).
- Data folder: `%LOCALAPPDATA%\BikeLog` on Windows, `~/.local/share/bikelog` elsewhere, or
  `--data-dir` / `BIKELOG_DATA_DIR`. A data folder inside the install folder is refused.
  Contents: `bikelog.db`, `backups/`, `exports/`, `logs/`, `strava.env` (Strava app details + tokens,
  owner-only, never in the DB), `demo/` (separate demo database for `--demo`).

---

## 3. Repository layout

```
README.md, HANDOVER.md, DECISIONS.md, TASKS.md      overview, test status, decisions (numbered), open work
UPDATING.md              Dirk's steps to git pull and rebuild on Windows, versions, releases (keep it current)
CHANGELOG.md             what changed per version; add to "## Unreleased" with every change
scripts/release.py       bump version, date changelog, commit "Release X.Y.Z", tag vX.Y.Z
requirements.txt / requirements-dev.txt / pyproject.toml
backend/bikelog/
  launcher.py            entry point and command-line commands
  catalog.py             component types, slots, maintenance actions, default rules, dispositions
  product_specs.py       spec fields per component type (drives the JSON import templates)
  models.py              SQLAlchemy models (mirror of the migrations)
  migrations/versions/   0001 core, 0002 Strava + specs, 0003 replacement/stock/work sessions, 0004 prices+journal,
                         0005 tire setup + rule condition + change log
  api/app.py, security.py
  services/              business logic (one module per area, see section 5)
  connectors/strava/     client.py (OAuth, retries, rate limits), sync.py (import), web.py (Settings flow)
  groupset_templates/    groupset data (one module per groupset)
  backup.py, paths.py, db.py, migrate.py, timeutil.py, single_instance.py
backend/tests/           pytest suites; fake_strava.py is an in-memory Strava API
frontend/src/            App.tsx, api.ts (fetch + token + op id), pages/*, components/*, types.ts, format.ts
e2e/smoke.cjs            browser test against the real running app; e2e/fixtures/ JSON files
docs/                    strava.md, groupsets.md, product-import.md, csv-import.md,
                         product-templates/ (generated JSON schemas/examples + AGENT_INSTRUCTIONS.md)
packaging/               bikelog.spec (PyInstaller), entry.py, bikelog.iss (Inno Setup), README.md, ci/ (inactive example)
```

---

## 4. Data model (tables in `models.py`)

- **bike**: name (unique), maker, model, status ACTIVE/RETIRED, `strava_gear_id`, `purchase_price_cents`,
  `purchase_date`, `shifting` (ELECTRONIC/MECHANICAL/NULL; `inventory.shifting_of`: NULL = electronic when a
  BATTERY is fitted, else unknown).
- **product**: what you can buy: `component_type`, maker, model, `specs_json`, `spec_source` (URL),
  `spec_version` (e.g. "JSON import ...; unverified"), `list_price_cents` (reference only).
- **component**: one physical part: type, label (unique per type), product, `prior_usage`
  (NEW/UNKNOWN/RECORDED), purchase date, `price_cents`, serial, status ACTIVE/RETIRED, `disposition`
  (STORED, AWAITING_SERVICE, RETIRED, DISCARDED, SOLD, VOIDED, IN_USE = rider gear such as shoes being worn), storage location,
  `purchase_session_id`, `from_stock_txn_id`.
- **installation**: a part on a bike slot or on a parent part (wheels on a wheelset; tire/tube/rotor/
  cassette/hub/spokes/rim tape/speed sensor on a wheel; bearings on a hub; chainrings on a crankset; quick
  link on a chain; upper/lower pulley wheels on a rear derailleur). Parents can nest; every part keeps its
  own km for a period `[installed, removed)`; voidable;
  `removal_outcome`; install/removal work-session ids. Overlaps are refused (service + DB triggers).
- **component_disposition**: history of what happened to a part off the bike (no deletes).
- **usage_adjustment**: starting mileage for a bike or part, with effective date and estimate flag.
- **ride**, **ride_source** (identity `(source kind, account, reference)` unique, so CSV export and API
  never double-count), **ride_override** (local edits survive re-import), **ride_equipment** (explicit
  part per slot for one ride; `ride.conditions` DRY/WET or null, local only, imports never touch it),
  **ride_flag** (uncertain/ambiguous), **usage_profile** (e.g. trainer:
  which slots/types get no km on VirtualRide).
- **usage_contribution**: rebuilt per ride: km per component per ride. All part mileage = sum of these
  + starting usage. Never edited by hand.
- **maintenance_event**: action on a part/bike: symptom, work done, outcome, measurement, consumable
  used, `cost_cents` (service fee), `work_session_id`; voidable.
- **service_rule** (trigger INTERVAL with km / months / ride hours (`interval_hours`, `warn_hours`), CYCLE
  window, PARENT_COUNT = number of parents served, `interval_count`, e.g. a quick link on its 2nd chain,
  or ONCE_AFTER_INSTALL = once after fitting, taken as done after `window_max_km`). Target: exactly one
  of `component_type` (type default; "BIKE" = bike-level default), `component_id` (one part) or `bike_id`
  (one bike). `requires_setup`: a tire setup (TUBE/TUBELESS/TUBULAR) or a shifting type
  (ELECTRONIC/MECHANICAL). **reminder_snooze** (on a part, or `bike_id` with no part).
- **consumable** (stock line: COUNTED stock of parts or BULK supplies, min stock, location) and
  **consumable_txn** (PURCHASE/USE/RETURN/ADJUST; only PURCHASE/RETURN carry money).
- **work_session**: groups the transactions of one action (replace, groupset import, maintenance,
  stock change) so it can be summarised and **undone as a whole**.
- **product_compatibility** (product ↔ bike, verified or not), **journal_entry** (dated NOTE/ISSUE on a
  bike or part, resolved date, voidable, no deletes; `ride_id` + `incident_type` (catalog.INCIDENT_TYPES) make
  it a ride incident; `incident_group` ties the entries of one incident together, one per affected part;
  `affected` names what was hit when it is not a recorded part: a body area or a position such as "Front tire"), **import_batch**, **operation** (idempotency),
  **strava_connection** (status, cursor, last success/error), **app_setting**.
- **component.tire_setup** (wheels only: TUBE/TUBELESS/TUBULAR; tires and tubes inherit it from their
  wheel via `inventory.tire_setup_of`), **service_rule.requires_setup** (rule only runs for that setup).
- **change_log**: one row per created/changed/installed/removed/voided/deleted event on a bike or part,
  old → new as readable text, `source` (APP, STRAVA, CSV_IMPORT, PRODUCT_IMPORT, DEMO) and `via` (op kind).
  Written by an `after_flush` hook in `bikelog/changelog.py` for every session, so new code is covered
  automatically; set the source with `change_source(...)` / `@from_source(...)` for non-UI writers.
  Plain ids (no FKs) so a deleted typo part keeps its rows; update/delete blocked by triggers.
- **purchase_bundle**: parts bought together at one price (a groupset): name, merchant, `purchased_on`,
  `price_cents`, notes, `work_session_id` (set by a groupset import, so undo voids it), voided/reason;
  delete blocked by a trigger. **component.bundle_id** links a member part; members carry no own price.

Migrations: plain `ADD COLUMN` / `CREATE TABLE` where possible; tables with protection triggers are not
rebuilt. Every schema upgrade writes a backup first; a database newer than the app is refused. A test
compares `models.py` with the migrated schema, so **every model change needs a new migration**
(never edit a released one; 0011 is the newest).

---

## 5. Core rules (services)

**Time.** Stored as UTC; date-only entries mean the start of the local day (timezone setting, default
Europe/Berlin). Installation periods are start-inclusive, end-exclusive. A ride on the day of a date-only
part change goes to the new part and is flagged ambiguous until confirmed.

**Mileage (`allocation.py`, `usage.py`).** For each ride, contributions are rebuilt from: the bike, the
installations covering the ride time (following parents: wheel → tire), explicit ride equipment, and the
usage profile (trainer rides skip wheels, tires, tubes, cassette, rotors, pads; the exclusion applies
to the whole path of parent slots, so everything below an excluded wheelset counts nothing too). Excluded rides count
nothing. Starting mileage before its effective date covers earlier rides. Unknown prior use shows "≥".

**Reminders (`maintenance.py`).** Rules per type with overrides per part. Defaults: hot wax every 500 km;
liquid-wax top-up once in the 250–300 km window after hot wax (never postpones hot wax); chain wear check
1000 km; brake fluid every 24 months (a bleed never resets it); pad check 1000 km; wheel inspection
3000 km/12 months; hub bearings 10000 km; freehub 5000 km/12 months; tire check 1000 km; sealant top-up every 3 months, tubeless only
(else NOT_APPLICABLE, hidden from the queue); headset service 5000 km/12 months. Part types include HEADSET and
POWER_METER (on the bike or on a crankset; actions zero offset, battery, firmware). Ride-hour rules
(`usage.hours_since`, rides without a moving time are counted and named): power meter
charge 50 h, Assioma pedals (POWER_PEDALS_CHARGE) 80 h (Dirk's choice; migration 0010 moves unedited
DEFAULT rows from 50 to 80), both warn 10 h, Magene-type speed sensor battery 400 h or 12 months. Di2 battery charge 800 km.
Charge rules (CHARGE_ACTIONS) say INSUFFICIENT_INFO until the first "Charged" is logged. Lever coin
cells (CR1632) 24 months, switched off by default (on only for wireless levers). Pulley wheels and
chainrings checked every 5000 km; quick link: PARENT_COUNT 2 chains; rim tape check 12 months.
**Yearly full service and tire pressure (migration 0010):** BIKE_FULL_SERVICE is a bike-level default
rule (12 months, warn 30 days) for the action FULL_SERVICE, whose `Action.checklist`
(`catalog.FULL_SERVICE_CHECKLIST`: hub bearings, headset, BB, brakes, Di2 wires / cables, frame and fork,
drivetrain, pedals, torque) is sent in `/api/meta` actions. The log form shows it as tick boxes and saves
"Done: …. Not done: …." in `work_done`; it resets only the full-service rule, never the per-part rules.
`component.pressure_note` (TIRE only, free text, max 80 characters, blank clears) is a note, not a
reminder: PATCH /api/components/{id} `pressure_note`; shown in the bike setup rows (`bike_setup`) and on
the part page (`PressureNote` in components/TireSetup.tsx).
**Coverage additions (migration 0009):** bike-level rules (`effective_bike_rules`, `bike_rule_status`,
`bike_status`, `set_bike_rule`; events with `bike_id` and no part): torque check every 3 months plus a
re-check after the first ride on any newly fitted `torque=True` part (specs from the product's
`torque_nm`), Di2 check 6 months and wire inspection 12 months (ELECTRONIC only). Attention items: a CRASH
incident until a FRAME_INSPECT is logged on or after its day; the hanger after a crash; cassette and
chainrings after a chain measured AT_LIMIT or taken off as discarded/retired (`_event_based_items`).
Measurements set the outcome from `Action.limits` when no outcome is picked
(`catalog.outcome_from_measurement`: pads 1.0 mm LOW / 0.5 AT_LIMIT and rotors 1.6/1.5 mm from Shimano;
chain 0.4 %/0.5 %). A wet ride since the last lube/wax makes a chain LUBRICATE rule DUE. Tire and bar-tape
rows show the age from the purchase date. Bed-in once after fitting pads/rotors (ONCE_AFTER_INSTALL, taken
as done after 100 km). Also: thru-axles 6 months, sealant renew 12 months (tubeless, Stan's), valve core
(tubeless), pedal bearings, BB check, bar tape, seatpost re-paste, hanger, hoses, cleats 2000 km, shift
cable/housing (MECHANICAL only), computer/light/radar charging by hours, lever coin cells 18 months (off).
Wheels without their own tube/tubeless setting use the setting `default_tire_setup` (TUBE).
**Rider gear** (`ComponentType.rider_gear`, SHOES): not installed; `set_disposition(IN_USE)` starts it and
STORED ends it; `AllocationIndex.rider` gives it (and the cleats mounted on it, slot path "RIDER") every
ride that has a bike while in use. Location text "worn → shoes".
Each due task
has a plain-language explanation. Snooze records no maintenance. Outcomes like AT_LIMIT/SPONGY/LEAK
raise attention until a later event.

**Replacement and inventory (`inventory.py`, `stock.py`, `spares.py`, `worksessions.py`).** Replace keeps
bike/slot, asks "What happened to the old item?" (defaults: pads, bar tape, quick links → discarded; tube
→ awaiting repair; others → stored spare). Sources for the new part: an existing spare, a new instance of
the same product, one unit from counted stock (stock − 1 and a new component in the same transaction), or
a newly described item. Move/swap positions keep identity and mileage. Replace takes `carry_over` (child parts moved to the new
part, e.g. the quick link onto the next chain); `replace_options.children` suggests it, off when the
child's PARENT_COUNT rule is due. A bike holds either two wheels or a wheelset, never both
(`_check_wheels_and_wheelset`); `group_wheels` puts both mounted wheels (with everything on them) into a
new WHEELSET part, which then moves as one. A part awaiting repair cannot be
installed until repaired. Inventory tabs: available spares, needs prep/repair, installed, shopping list
(from minimum stock), history. Undo of a work session is refused if later records depend on it; parts it
created stay as "record of an undone operation".

**Costs (`costs.py`).** Initial cost = bike purchase price. Running cost is derived each time: part prices
(counted for the bike the part was *first* installed on, following parents; spares never installed count
for no bike), stock used on the bike valued at the stock line's average purchase price (≈), and service
costs on maintenance entries (a multi-part entry stores one fee once). Undone sessions drop out. Parts that
came with the bike should have no price (they are inside the purchase price). **Bundles
(`bundles.py`)**: the bundle price counts once, for the bike most of its members were first installed on;
members have no own price (refused while the bundle is live) and their per-part share (weighted by product
reference price, else even; rounding to the largest) is an estimate for display only. Replacement parts
bought later carry their own price; the original members stay in the bundle (retired or stored). A part
with its own price, from stock, or in another live bundle cannot join. Voiding frees the members.
Groupset import takes `bundle` (one price) or `prices` (per part), never both, and `to_spares` (keys kept
in storage although a bike is chosen, e.g. a BSA bottom bracket that does not fit).

**Journal (`journal.py`).** Dated notes/issues on bikes and parts; a part's entry also records its bike;
maintenance notes (symptom, work done, notes) appear in the same list read-only. A part's journal also
shows entries of parts mounted below it on the entry date (`via_child`: a flat on the tire shows on the
wheel and the wheelset). Ride incidents: `journal.add(ride_id, incident_type, component_id)` sets date,
bike and default text from the ride; `entries(ride_id=)`, `incidents(bike_id, incident_type, open_only)`.
**Ride incidents (`incidents.py`, migration 0011).** `catalog.INCIDENT_OPTIONS` lists, per incident type,
what it can affect (`IncidentOption`: component types, plus `within` slots for front/rear; no types = a body
area, e.g. FIT). `choices(ride, type)` resolves them against `parts_on_ride` (installation tree on the ride
date, plus the parts the ride counted on): one choice per matching part (key `c<id>`), or the option's
name when no such part is recorded (key = option key, stored in `affected`); `BIKE` = whole bike. DEFECT and
OTHER offer every part. `log` writes one journal issue per picked key with a shared `incident_group`;
`update` edits type/details/fixed date/affected (unticked entries are voided "taken out of the incident",
new ones added to the group); `remove` voids all ("incident removed"), `restore` brings those back. The
ride's incident count counts groups. Solved / Re-open on the ride = PATCH `incidents/{group}` with
`resolved_on` today / null (the whole incident, every affected part).
**Ride summary.** `rides.ride_detail` adds `summary` (`ride_summary`: this ride's km/hours; the bike's
total km from `bike_usage` incl. starting value, hours from recorded ride time, and this calendar year and
month in the app timezone via `_period`) and `hours` per equipment row (contribution `duration_s`). UI:
`RideSummaryStats` in pages/Rides.tsx; the parts table is behind "Show details".
**Bike page layout.** pages/Bikes.tsx `BikeDetailPage`: header card (only "Record work done" = LogMaintenance), then tabs (`?tab=` overview |
rides | incidents | maintenance | costs | history; Rides = `BikeRides`, GET `rides?view=active&bike_id=`,
a click opens `RideDetailView` (exported from pages/Rides.tsx) in a Sheet). `SetupGroups` folds "Installed now" into `<details
class="setup-group" data-group=…>` by the category of each top-level part (Drivetrain/Brakes/Controls and
BATTERY → GROUPSET, Wheels, Cockpit, Contact points, Frame, Electronics, Other); parts mounted on parts stay
with their root. `ServiceStatus` shows OVERDUE/DUE/DUE_SOON/ATTENTION/SNOOZED, and folds INSUFFICIENT_INFO
and the rest into `details.task-group`. `ManageParts` (top of the overview tab) holds the swaps (Swap chain/wheels or wheelset/tire/another part → `SwapPart` picks the installed row, then `ReplaceForm`), Install a part, Add groupset and Group wheels. replace-options gives each spare `mounted` (parts already on it); ReplaceForm leaves children whose slot is taken there unticked (DECISIONS 83). **Flats and spares.** FLAT choices carry `wheel`/`damage`; `FlatDamage` in components/Incidents.tsx turns "tube only / tube and tire" into keys (no tube on tubeless/tubular wheels, `_wheels_without_tube`). Rides list counts distinct incident_group. `stock.spare_check` (setting `spare_minimums`, GET /api/spares/check) feeds `stock.shopping_list` (entries with consumable_id null) and /api/overview (`shopping_list`, `spares`); Settings → Spares to keep edits it. Overview = `UpcomingTasks` + `ShoppingCard`, other cards folded (DECISIONS 84–86). **Fixing incidents.** services/repairs.py: `describe` (PART / POSITION / OTHER per affected entry), `fix_options`, `fix` (one work session; REPLACED via inv.replace or `replace_at_position`, REPAIRED = TUBE_PATCH for tracked tubes), `undo_fix`; `worksessions.undo` calls `repairs.clear_for_session`. API: GET incidents/{group}/fix-options, POST incidents/{group}/fix and /undo-fix, GET bikes/{id}/position-options, POST bikes/{id}/swap-position. UI: components/Repairs.tsx (`FixForm`, `SwapTube`); IncidentRows shows Fix / Undo fix and the repair lines; Overview Upcoming tasks lists open incidents (/api/overview `open_incidents`). Migration 0012 (DECISIONS 87–88). **Where a part goes.** `spares.mount_targets(component_type, bike_id=None)` (GET /api/mount-targets) lists bike positions and parent parts with path and occupant; `catalog.ON_BIKE_TOO` lists parent-type parts that may also sit on the bike. UI: components/MountPicker.tsx, used by ComponentForm (Inventory → Add part, with "Keep as a spare") and InstallForm (bike page). DECISIONS 89. Incidents tab: GET `bikes/{id}/incidents`
(`incidents.bike_incidents`, open first) rendered by `BikeIncidents` (shared `IncidentRows`; Edit loads
the choices of the incident's ride). e2e helpers `setupItem`, `openGroups`, `openTaskGroups`, `bikeTab`. UI: components/Incidents.tsx (`RideIncidents`, `IncidentEditor`).

---

## 6. Features and where they live

| Feature | Backend | UI | Docs |
|---|---|---|---|
| Bikes, parts, install/remove/replace/move, chains A/B/C | inventory.py | pages/Bikes.tsx, Inventory.tsx, components/PartChange.tsx | DECISIONS 7–11, 14–23 |
| Rides area (tabs Rides / No bike / Removed rides), bike per ride or in bulk, remove/restore, starting mileage, ledger ("where the km come from") | rides.py, allocation.py, usage.py | pages/Rides.tsx | DECISIONS 40–42 |
| Maintenance, rules, snooze, brakes, chain wax cycle | maintenance.py, catalog.py | pages/Maintenance.tsx, components/LogMaintenance.tsx, TaskList.tsx | DECISIONS 12–13 |
| Spare parts, stock, supplies, shopping list, undo | stock.py, spares.py, worksessions.py | pages/Inventory.tsx | DECISIONS 14–23 |
| Groupset import (12 templates: Shimano Ultegra/Dura-Ace/105 Di2, 105 mechanical, GRX; SRAM RED/Force/Rival/Apex, RED/Force XPLR 13-speed) | services/groupsets.py, groupset_templates/ | components/GroupsetImport.tsx (bike page → Add groupset) | docs/groupsets.md, DECISIONS 28–30 |
| Prices, initial/running cost | costs.py | bike list, bike page Costs card, part Edit details | DECISIONS 31–34 |
| Purchase bundles (groupset bought at one price), parts kept as spares at import | services/bundles.py, groupsets.py, costs.py | components/Bundles.tsx (bike page "Bought as a bundle"), GroupsetImport.tsx, part page | docs/groupsets.md, DECISIONS 51–52 |
| Km from before (starting mileage of a part, e.g. a wheelset from another bike) | inventory.set_starting_usage, usage.py | part page → Starting km / "Add km from before"; Add part form | DECISIONS 53 |
| Journal | journal.py | components/Journal.tsx (bike and part pages) | DECISIONS 35 |
| Ride incidents (13 types, each with its own affected parts or body areas, several per incident; edit, remove, restore), dry/wet per ride | incidents.py, journal.py, rides.py | components/Incidents.tsx (ride detail; Rides → Incidents tab) | DECISIONS 55–56, 78–80 |
| Parts inside parts: wheelset → wheels → tire/hub/bearings/spokes/sensor; pulleys on the rear derailleur; carry-over at replace | inventory.py (group_wheels, replace carry_over), allocation.py, spares.py | Bikes.tsx ("Group wheels into a wheelset"), PartChange.tsx | DECISIONS 57–58 |
| Ride-hour, number-of-chains and charging reminders | maintenance.py, usage.hours_since, catalog.py | Inventory.tsx RuleEditor (hours/count fields) | DECISIONS 59–61 |
| Whole-bike reminders (torque, Di2, crash → frame inspection), measurement limits, bed-in, wet ride, worn chain → cassette, shifting type, default tire setup | maintenance.py (bike_status, _event_based_items), catalog.py (Limit) | TaskList.tsx (whole-bike rows), LogMaintenance.tsx (bike-level actions, outcome hint), Bikes.tsx (Shifting), Settings.tsx (Default tire setup) | DECISIONS 62–67 |
| Shoes and cleats (count every ride while in use) | allocation.py (rider periods), inventory.set_disposition IN_USE | Inventory.tsx part page "Start using / Stop using" | DECISIONS 66 |
| Change log | changelog.py | components/ChangeLog.tsx (bike and part pages) | DECISIONS 45 |
| Tube/tubeless on wheels, sealant reminder | inventory.tire_setup_of, maintenance.py, catalog.py | components/TireSetup.tsx (bike setup rows, wheel page) | DECISIONS 43–44 |
| Diagnostics log | logging_setup.py, services/diagnostics.py | components/Diagnostics.tsx (Settings) | DECISIONS 46 |
| Versioning (one number in bikelog/__init__.py; release vs 0.2.0+commit) | buildinfo.py, scripts/release.py, packaging/bikelog.spec + bikelog.iss | App.tsx (v0.2.0 by the logo), components/VersionInfo.tsx | DECISIONS 50, CHANGELOG.md, UPDATING.md |
| Build/version check (app vs screens commit) | buildinfo.py, packaging/bikelog.spec, frontend/vite.config.ts | components/VersionInfo.tsx, version.ts (red bar in App.tsx) | DECISIONS 48, UPDATING.md |
| JSON product import (one template per part type) | product_import.py, product_specs.py | components/ProductImport.tsx (Inventory → Import JSON) | docs/product-import.md, docs/product-templates/AGENT_INSTRUCTIONS.md, DECISIONS 36–38 |
| CSV ride import (generic + Strava export), resumable | imports.py | pages/Settings.tsx | docs/csv-import.md |
| Strava API sync | connectors/strava/ | components/StravaSettings.tsx (Settings → Strava) | docs/strava.md, DECISIONS 26, 39, 42 |
| Backups, export/restore, demo mode | backup.py, services/demo.py | Settings | DECISIONS 4–5 |
| Sample database on first start (2 made-up bikes, rides, incidents; banner until Fresh start) | services/demo.py `seed_sample`, launcher.prepare(sample=), setting `sample_data` | App.tsx banner, components/FreshStart.tsx | DECISIONS 74 |
| Fresh start (reset database) and restore of any backup while the app runs | reset.py, backup.KEPT_MARK | components/FreshStart.tsx, Settings → Backups "Restore" | DECISIONS 54 |

Strava details: full API sync with permanent storage (Dirk's choice). Credentials and tokens live only in
`<data dir>/strava.env`; the secret is write-only in the UI and never logged. OAuth callback
`http://localhost:<port>/api/strava/callback` with a single-use state (Strava app setting "Authorization
Callback Domain" = `localhost`). Rides map to bikes by `strava_gear_id`; unknown gear links a bike with the
same name or creates one. Sync is resumable (cursor written with each page), looks back 30 days from the
cursor so gear changed on Strava is picked up, and runs in the background after a backup. Disconnect keeps
all rides (`mark_disconnected`).

Rides and the bike: the user's bike choice (or "no bike") is a `ride_override` on field `bike_id`
(`rides.assign_bike`, `POST /api/rides/assign-bike` with `ride_ids` and `bike_id` or null). Overrides win
over source values in `apply_effective`, so sync, Re-read and CSV re-import keep them; `ride_row` reports
`bike_overridden` and the source's bike. "Remove ride" = `/exclude`: `inclusion` EXCLUDED, the source
identity stays, so imports skip it; `/restore` brings it back. `GET /api/rides?view=active|removed|all`
and `unassigned=true` drive the three tabs.

Ride flags (`allocation._plan` / `allocate_ride`, table `ride_flag`, rebuilt on every allocation): NO_BIKE,
AMBIGUOUS_CHANGE_DATE, NO_WHEELS (road ride, bike has parts but no wheel at that moment), BEFORE_PURCHASE
(ride date < bike.purchase_date; `update_bike` re-allocates when the purchase date changes),
MISSING_DISTANCE, UNCERTAIN_ASSIGNMENT. `ride_detail.counting_note` explains a ride that adds no km
(inside the bike's starting km, or inside every part's km from before). `bike_usage.ride_count` leaves out
rides before the bike's starting value (`rides_before_start`). A CSV bike name with no match goes into
the source values as `unmatched_bike`, sets the ride uncertain with a note, and is counted in the import
result's `unknown_bikes`. Interval reminders report `km_at_least` when the last service is older than the
part's "km from before" date. **Only ever tested against `tests/fake_strava.py`; no live Strava call has been made.**

Groupset templates: shared building blocks in `groupset_templates/_shared.py`; an item may carry `rules`
(per-part version of a default rule, applied with `maintenance.set_component_rule` at import). BATTERY can
mount on a front or rear derailleur (SRAM AXS). All templates are unverified.
Groupset template data for Ultegra R8100 came from retailer listings (shimano.com was unreachable from the
cloud environment) and is marked unverified in the app.

---

## 7. Build, run, test

Development (Linux/macOS shown; on Windows use `.venv\Scripts\python`):

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cd backend && ../.venv/bin/python -m bikelog            # http://127.0.0.1:8765/
../.venv/bin/python -m bikelog --demo                   # separate demo database
```
Tooling notes: the test client needs `httpx2` (requirements-dev.txt; plain httpx gives a Starlette
deprecation warning). eslint 10 with react-hooks 7 runs only `rules-of-hooks` and `exhaustive-deps`.
A dependency with an install script needs an `allowScripts` entry in frontend/package.json (npm 11
warns, npm 12 blocks): run `npm install-scripts approve <pkg>`.

Checks that must pass before every push:

```bash
.venv/bin/python -m pytest -q backend/tests             # currently 180 passed
cd frontend && npx tsc -b && npx eslint . && npx vite build
# browser test: start the app on a fresh data dir, then
node e2e/smoke.cjs http://127.0.0.1:8790/ <screenshot-dir>   # currently 86/86 (the ride-form step can flake once; rerun)
#   (cd backend && ../.venv/bin/python -m bikelog --no-browser --no-sample --port 8790 --data-dir <fresh dir>)
# sample database: start on ANOTHER fresh dir WITHOUT --no-sample (port 8791), then
node e2e/sample.cjs http://127.0.0.1:8791/ <screenshot-dir>  # banner, sample bikes, crash item, Fresh start
```

The e2e script expects a fresh data directory. Playwright with Chromium must be available.
If you change spec fields (`product_specs.py`), regenerate the templates:
`python -m bikelog --write-product-templates docs/product-templates` (a test fails otherwise).

### Windows build (Dirk's PC, PowerShell, from the repository folder)

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
cd frontend; npm ci; npm run build; cd ..
.venv\Scripts\pyinstaller --noconfirm --clean packaging\bikelog.spec     # → dist\BikeLog\BikeLog.exe
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\bikelog.iss  # → dist\installer\BikeLog-0.1.0-<commit>-setup.exe
```

`packaging/build.ps1` runs all of this (plus git pull and tests) and stops at the first error; the
installer file name carries the git commit. PowerShell needs `&` before a quoted exe path. Inno Setup installed via winget lands in
`%LOCALAPPDATA%\Programs\Inno Setup 6`. Dirk has compiled the exe and installer on 2026-10-25; the
install/launch checklist in `packaging/README.md` is still pending, and nothing was tested on a clean
Windows machine without Python. The app is unsigned (SmartScreen warns).

Updating an existing build after new commits (close app, pull, rebuild, reinstall; data is kept) is
described for Dirk in `UPDATING.md`. Every change you push must keep that file correct.

---

## 8. Command line (the app must be closed for commands that change data)

`--data-dir PATH`, `--port N`, `--no-browser`, `--no-sample` (a new database starts empty), `--demo`, `--backup`, `--export [FILE]`, `--restore FILE`,
`--strava-connect`, `--strava-sync`, `--strava-rescan`, `--strava-disconnect`,
`--import-products FILE... [--dry-run]`, `--write-product-templates DIR`, `--version`.
Dirk prefers doing everything in the app UI; keep UI paths for every feature.

---

## 9. HTTP API (all under `/api`, JSON)

Meta/overview: `health`, `meta`, `overview`, `settings` (GET/PATCH). Bikes: `bikes` (GET/POST),
`bikes/{id}` (GET/PATCH), `/retire`, `/starting-usage`. Products: `products` (GET/POST), `products/{id}`
(PATCH), `/compatibility`. Components: `components` (GET/POST), `components/{id}` (GET/PATCH/DELETE*),
`/install`, `/remove`, `/replace-options`, `/replace`, `/move-targets`, `/move`, `/disposition`, `/retire`,
`/starting-usage`, `/correction`, `/rules`; `installations/{id}/void|correct`. Rides: `rides` (GET/POST),
`rides` GET takes `view` (active/removed/all), `unassigned`, `bike_id`, `flagged`; `rides/assign-bike`
(POST, several rides, `bike_id` null = no bike); `rides/{id}` (GET/PATCH), `/exclude` (= Remove ride), `/restore`, `/equipment/{slot}` (PUT/DELETE). Maintenance:
`maintenance/queue|events|candidates`, `events` POST, `/void`, `snooze`; `rules`; `chains`; `brakes`.
Stock: `consumables` (GET/POST/PATCH), `/txns`, `/txn`, `/install`; `inventory`; `shopping-list`.
Work sessions: `work-sessions`, `/{id}`, `/{id}/undo`. Journal: `journal` (GET/POST), `/{id}` PATCH,
`/{id}/void`; `journal?ride_id=`; `incidents` (GET `bike_id`, `incident_type`, `open_only`);
`rides/{id}/incidents` (GET incidents + choices per type, POST `incident_type`, `affected` keys, `text`,
`resolved_on`), `bikes/{id}/incidents` (GET), GET `incidents` returns one row per incident (`incidents.all_incidents`; a bike/part filter picks incidents touching it, the row lists everything affected), `incidents/{group}` (PATCH), `incidents/{group}/remove|restore` (POST); `bikes/{id}/group-wheels` (POST);
`bikes/{id}/rules` (GET, bike-level rules with status), `bikes/{id}/rules/{rule_code}` (PATCH, per bike);
`maintenance/snooze` takes `bike_id` for a bike-level reminder; bikes take `shifting`. Groupsets: `groupsets`, `/{code}/plan`, `/{code}/import`. Bundles: `bundles` (GET `bike_id`, `include_voided`; POST),
`bundles/candidates`, `bundles/{id}` (GET/PATCH), `/members` (POST), `/members/{cid}` (DELETE), `/void`. Imports: `imports/csv`,
`imports`, `imports/template`, `imports/products`, `product-templates`, `product-templates/{type}/schema|example`,
`product-templates/instructions.md`. Strava: `strava/status`, `credentials` (PUT/DELETE), `connect`,
`callback`, `sync`, `disconnect`. History/diagnostics: `changes?bike_id=|component_id=`, `logs?lines=&level=`,
`logs/download`. Data: `backups` (GET/POST; rows carry `kept`), `backups/{name}/restore` (POST), `exports` (POST, GET file),
`admin/rebuild`, `admin/reset` (POST `{confirm: "RESET", clear_strava}`).
(*DELETE of a component is refused once it has installations, usage or maintenance; such parts are retired instead.)

---

## 10. Git and working rules

- Repository: `github.com/dirksachse74/bike_log` (**private**). Work only on the feature branch
  `claude/project-thread-6y3mmh` (or a branch Dirk names). **Never push to `main`, never merge into it,
  never force-push, never change repository visibility, never deploy anything.**
- Before every push: run all checks (section 7) and scan for secrets; never commit `.env`/`strava.env`,
  databases, backups, exports or personal ride data. Demo data uses fictional Strava gear ids.
- The cloud environment can push the feature branch but not tags (the push is refused). After a release
  there, Dirk pushes the tag from his PC: `git fetch origin; git tag -a vX.Y.Z <commit> -m "Bike Log X.Y.Z";
  git push origin vX.Y.Z` (v0.2.0 = e95b486 was made this way).
- Add every user-visible change to CHANGELOG.md under "## Unreleased". Make a release (scripts/release.py)
  only when Dirk asks; the version lives only in `backend/bikelog/__init__.py`.
- Dirk's standing rule: with every change, update the docs and this guide in the same commit, push the
  feature branch, and tell him it is pushed and what to pull and rebuild (`UPDATING.md`).
- Commit in small, described steps and push at checkpoints so no work is lost.
- Keep `DECISIONS.md` (add a numbered entry for each reversible decision), `TASKS.md` and `HANDOVER.md`
  (test counts and status) up to date with every feature.
- Do not weaken or skip tests or replace real behaviour with mocks to get green results.
- Do not describe anything as working on Windows or with the real Strava until it was actually run there.

### Secrets

Dirk once pasted Strava API credentials into a chat; he was told to **reset the Client Secret** on
strava.com before use. Never use, store or repeat credentials from chats. The only place for Strava
details is `strava.env` on his PC, entered through Settings → Strava.

---

## 11. Open decisions and what still needs verifying

Needs Dirk or his machine:

1. **Windows**: run the installer and the checklist in `packaging/README.md` (install, launch, data entry,
   restart, second start, data location, backup); later a clean machine without Python.
2. **Strava live**: reset secret, set callback domain `localhost`, connect and sync from Settings; check
   gear-to-bike matching, bike overrides and VirtualRide handling with his real data.
3. **Strava API terms**: the full 2026 terms (7-day cache rule, storage of derived data) were never read;
   permanent storage is his explicit choice at his own risk (DECISIONS 26).
4. **Ultegra R8100 template**: verify specs against productinfo.shimano.com, then mark it verified.
5. Same-day maintenance vs ride order: currently maintenance counts *before* a ride on the same date
   (DECISIONS 13), open question.

Open work (TASKS.md): editing stock line details and product compatibility/reference price in the UI
(APIs exist), possible-duplicate ride merge helper, more groupset templates, a cost report across bikes
per year, app icon and code signing, optional Windows CI build (needs Dirk's OK).

Out of scope until asked: barcode scanning, automatic ordering, any cloud hosting or multi-user use.

---

## 12. How to start as the next agent

1. Clone the repo, check out the feature branch, read this file, `DECISIONS.md`, `TASKS.md`, `HANDOVER.md`.
2. Set up the environment (section 7) and run all checks; they should all pass before you change anything.
3. For a new feature: service logic + migration (if the schema changes) + API + UI + tests (pytest and a
   step in `e2e/smoke.cjs`) + docs/DECISIONS/TASKS/HANDOVER, then push to the feature branch.
4. Report to Dirk in plain words: what changed, how it was tested, what he has to do (usually `git pull`
   and rebuild), and what is still unverified.
