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
   enforce this for history tables). Exception: disconnecting Strava deletes API-imported rides
   (Strava terms), after a backup.
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
requirements.txt / requirements-dev.txt / pyproject.toml
backend/bikelog/
  launcher.py            entry point and command-line commands
  catalog.py             component types, slots, maintenance actions, default rules, dispositions
  product_specs.py       spec fields per component type (drives the JSON import templates)
  models.py              SQLAlchemy models (mirror of the migrations)
  migrations/versions/   0001 core, 0002 Strava + specs, 0003 replacement/stock/work sessions, 0004 prices+journal
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
  `purchase_date`.
- **product**: what you can buy: `component_type`, maker, model, `specs_json`, `spec_source` (URL),
  `spec_version` (e.g. "JSON import ...; unverified"), `list_price_cents` (reference only).
- **component**: one physical part: type, label (unique per type), product, `prior_usage`
  (NEW/UNKNOWN/RECORDED), purchase date, `price_cents`, serial, status ACTIVE/RETIRED, `disposition`
  (STORED, AWAITING_SERVICE, RETIRED, DISCARDED, SOLD, VOIDED), storage location,
  `purchase_session_id`, `from_stock_txn_id`.
- **installation**: a part on a bike slot or on a parent part (tire/tube/rotor/cassette on a wheel,
  chainring on a crankset, quick link on a chain) for a period `[installed, removed)`; voidable;
  `removal_outcome`; install/removal work-session ids. Overlaps are refused (service + DB triggers).
- **component_disposition**: history of what happened to a part off the bike (no deletes).
- **usage_adjustment**: starting mileage for a bike or part, with effective date and estimate flag.
- **ride**, **ride_source** (identity `(source kind, account, reference)` unique, so CSV export and API
  never double-count), **ride_override** (local edits survive re-import), **ride_equipment** (explicit
  part per slot for one ride), **ride_flag** (uncertain/ambiguous), **usage_profile** (e.g. trainer:
  which slots/types get no km on VirtualRide).
- **usage_contribution**: rebuilt per ride: km per component per ride. All part mileage = sum of these
  + starting usage. Never edited by hand.
- **maintenance_event**: action on a part/bike: symptom, work done, outcome, measurement, consumable
  used, `cost_cents` (service fee), `work_session_id`; voidable.
- **service_rule** (interval km/months or cycle window), **reminder_snooze**.
- **consumable** (stock line: COUNTED stock of parts or BULK supplies, min stock, location) and
  **consumable_txn** (PURCHASE/USE/RETURN/ADJUST; only PURCHASE/RETURN carry money).
- **work_session**: groups the transactions of one action (replace, groupset import, maintenance,
  stock change) so it can be summarised and **undone as a whole**.
- **product_compatibility** (product ↔ bike, verified or not), **journal_entry** (dated NOTE/ISSUE on a
  bike or part, resolved date, voidable, no deletes), **import_batch**, **operation** (idempotency),
  **strava_connection** (status, cursor, last success/error), **app_setting**.

Migrations: plain `ADD COLUMN` / `CREATE TABLE` where possible; tables with protection triggers are not
rebuilt. Every schema upgrade writes a backup first; a database newer than the app is refused. A test
compares `models.py` with the migrated schema, so **every model change needs a new migration**
(never edit a released one; 0004 is the newest).

---

## 5. Core rules (services)

**Time.** Stored as UTC; date-only entries mean the start of the local day (timezone setting, default
Europe/Berlin). Installation periods are start-inclusive, end-exclusive. A ride on the day of a date-only
part change goes to the new part and is flagged ambiguous until confirmed.

**Mileage (`allocation.py`, `usage.py`).** For each ride, contributions are rebuilt from: the bike, the
installations covering the ride time (following parents: wheel → tire), explicit ride equipment, and the
usage profile (trainer rides skip wheels, tires, tubes, cassette, rotors, pads). Excluded rides count
nothing. Starting mileage before its effective date covers earlier rides. Unknown prior use shows "≥".

**Reminders (`maintenance.py`).** Rules per type with overrides per part. Defaults: hot wax every 500 km;
liquid-wax top-up once in the 250–300 km window after hot wax (never postpones hot wax); chain wear check
1000 km; brake fluid every 24 months (a bleed never resets it); pad check 1000 km; wheel inspection
3000 km/12 months; hub bearings 10000 km; freehub 5000 km/12 months; tire check 1000 km. Each due task
has a plain-language explanation. Snooze records no maintenance. Outcomes like AT_LIMIT/SPONGY/LEAK
raise attention until a later event.

**Replacement and inventory (`inventory.py`, `stock.py`, `spares.py`, `worksessions.py`).** Replace keeps
bike/slot, asks "What happened to the old item?" (defaults: pads, bar tape, quick links → discarded; tube
→ awaiting repair; others → stored spare). Sources for the new part: an existing spare, a new instance of
the same product, one unit from counted stock (stock − 1 and a new component in the same transaction), or
a newly described item. Move/swap positions keep identity and mileage. A part awaiting repair cannot be
installed until repaired. Inventory tabs: available spares, needs prep/repair, installed, shopping list
(from minimum stock), history. Undo of a work session is refused if later records depend on it; parts it
created stay as "record of an undone operation".

**Costs (`costs.py`).** Initial cost = bike purchase price. Running cost is derived each time: part prices
(counted for the bike the part was *first* installed on, following parents; spares never installed count
for no bike), stock used on the bike valued at the stock line's average purchase price (≈), and service
costs on maintenance entries (a multi-part entry stores one fee once). Undone sessions drop out. Parts that
came with the bike should have no price (they are inside the purchase price).

**Journal (`journal.py`).** Dated notes/issues on bikes and parts; a part's entry also records its bike;
maintenance notes (symptom, work done, notes) appear in the same list read-only.

---

## 6. Features and where they live

| Feature | Backend | UI | Docs |
|---|---|---|---|
| Bikes, parts, install/remove/replace/move, chains A/B/C | inventory.py | pages/Bikes.tsx, Inventory.tsx, components/PartChange.tsx | DECISIONS 7–11, 14–23 |
| Rides, starting mileage, ledger ("where the km come from") | rides.py, allocation.py, usage.py | pages/Rides.tsx | |
| Maintenance, rules, snooze, brakes, chain wax cycle | maintenance.py, catalog.py | pages/Maintenance.tsx, components/LogMaintenance.tsx, TaskList.tsx | DECISIONS 12–13 |
| Spare parts, stock, supplies, shopping list, undo | stock.py, spares.py, worksessions.py | pages/Inventory.tsx | DECISIONS 14–23 |
| Groupset import (Shimano Ultegra Di2 R8100) | services/groupsets.py, groupset_templates/ | components/GroupsetImport.tsx (bike page → Add groupset) | docs/groupsets.md, DECISIONS 28–30 |
| Prices, initial/running cost | costs.py | bike list, bike page Costs card, part Edit details | DECISIONS 31–34 |
| Journal | journal.py | components/Journal.tsx (bike and part pages) | DECISIONS 35 |
| JSON product import (one template per part type) | product_import.py, product_specs.py | components/ProductImport.tsx (Inventory → Import JSON) | docs/product-import.md, docs/product-templates/AGENT_INSTRUCTIONS.md, DECISIONS 36–38 |
| CSV ride import (generic + Strava export), resumable | imports.py | pages/Settings.tsx | docs/csv-import.md |
| Strava API sync | connectors/strava/ | components/StravaSettings.tsx (Settings → Strava) | docs/strava.md, DECISIONS 26, 39 |
| Backups, export/restore, demo mode | backup.py, services/demo.py | Settings | DECISIONS 4–5 |

Strava details: full API sync with permanent storage (Dirk's choice). Credentials and tokens live only in
`<data dir>/strava.env`; the secret is write-only in the UI and never logged. OAuth callback
`http://localhost:<port>/api/strava/callback` with a single-use state (Strava app setting "Authorization
Callback Domain" = `localhost`). Rides map to bikes by `strava_gear_id`; unknown gear links a bike with the
same name or creates one. Sync is resumable (cursor written with each page), runs in the background after
a backup. **Only ever tested against `tests/fake_strava.py`; no live Strava call has been made.**

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

Checks that must pass before every push:

```bash
.venv/bin/python -m pytest -q backend/tests             # currently 104 passed
cd frontend && npx tsc -b && npx eslint . && npx vite build
# browser test: start the app on a fresh data dir, then
node e2e/smoke.cjs http://127.0.0.1:8790/ <screenshot-dir>   # currently 44/44
#   (cd backend && ../.venv/bin/python -m bikelog --no-browser --port 8790 --data-dir <fresh dir>)
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
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\bikelog.iss  # → dist\installer\BikeLog-0.1.0-setup.exe
```

PowerShell needs `&` before a quoted exe path. Inno Setup installed via winget lands in
`%LOCALAPPDATA%\Programs\Inno Setup 6`. Dirk has compiled the exe and installer on 2026-10-25; the
install/launch checklist in `packaging/README.md` is still pending, and nothing was tested on a clean
Windows machine without Python. The app is unsigned (SmartScreen warns).

---

## 8. Command line (the app must be closed for commands that change data)

`--data-dir PATH`, `--port N`, `--no-browser`, `--demo`, `--backup`, `--export [FILE]`, `--restore FILE`,
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
`rides/{id}` (GET/PATCH), `/exclude`, `/restore`, `/equipment/{slot}` (PUT/DELETE). Maintenance:
`maintenance/queue|events|candidates`, `events` POST, `/void`, `snooze`; `rules`; `chains`; `brakes`.
Stock: `consumables` (GET/POST/PATCH), `/txns`, `/txn`, `/install`; `inventory`; `shopping-list`.
Work sessions: `work-sessions`, `/{id}`, `/{id}/undo`. Journal: `journal` (GET/POST), `/{id}` PATCH,
`/{id}/void`. Groupsets: `groupsets`, `/{code}/plan`, `/{code}/import`. Imports: `imports/csv`,
`imports`, `imports/template`, `imports/products`, `product-templates`, `product-templates/{type}/schema|example`,
`product-templates/instructions.md`. Strava: `strava/status`, `credentials` (PUT/DELETE), `connect`,
`callback`, `sync`, `disconnect`. Data: `backups` (GET/POST), `exports` (POST, GET file), `admin/rebuild`.
(*DELETE of a component is refused once it has installations, usage or maintenance; such parts are retired instead.)

---

## 10. Git and working rules

- Repository: `github.com/dirksachse74/bike_log` (**private**). Work only on the feature branch
  `claude/project-thread-6y3mmh` (or a branch Dirk names). **Never push to `main`, never merge into it,
  never force-push, never change repository visibility, never deploy anything.**
- Before every push: run all checks (section 7) and scan for secrets; never commit `.env`/`strava.env`,
  databases, backups, exports or personal ride data. Demo data uses fictional Strava gear ids.
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
   gear-to-bike matching and VirtualRide handling with his real data.
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
