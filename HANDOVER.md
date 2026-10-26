# Handover

Repository: https://github.com/dirksachse74/bike_log (private) · branch `claude/project-thread-6y3mmh`
State as of 2026-10-25 (latest commit: see `git log -1` on the branch).

## What works (tested in the build environment: Linux x86_64, Python 3.13, Node 22)
- **Bikes, parts, installations**: products vs physical parts, install/remove/replace/move with
  effective dates, conflict protection, lifetime mileage across bikes, chains labelled A/B/C.
- **Rides**: Rides area with tabs Rides / No bike / Removed rides; bike per ride or for several rides
  (kept across Strava and CSV re-imports); removed rides are restorable and never re-imported;
  manual rides, edit/remove/restore with exact-once totals, starting mileage with estimate
  flag, uncertain assignments, "where the kilometres come from" ledger, trainer profile.
- **Maintenance**: hot wax every 500 km, one liquid top-up per 250–300 km window, wear checks,
  brake circuits front/rear independent, bleed vs full fluid replacement, wheel/bearing/freehub rules,
  snooze, explanation for every due task.
- **Spare parts and replacement**: Replace button with preselected bike/position/outgoing part,
  "What happened to the old item?", stock counts per product, install from stock, tube patch and
  return to spares, bar tape rewrap, tire position change and swap, undo of a whole work session,
  shopping list from minimum stock, purchases/returns/corrections, compatibility labels.
- **Groupset import**: Bike → Add groupset creates every part of Shimano Ultegra Di2 R8100 in one
  undoable step, placed on the bike, its wheels and the new crankset/chain (docs/groupsets.md).
- **Costs**: purchase price per bike (initial cost) and running cost added up from part prices, stock
  used and service costs, counted once; shown on the bike list and the bike page with cost per km.
- **Journal**: dated notes and issues on every bike and part, with maintenance notes in the same list.
- **Change log**: every change to a bike or part (old → new, when, who) on its page; cannot be edited.
- **Tire setup and time reminders**: tube/tubeless set on the wheel (moves with it); sealant top-up every
  3 months for tubeless, brake fluid every 24 months. Headset and power meter part types.
- **Diagnostics**: Settings shows and downloads the log (secrets removed).
- **JSON product import**: products and spare parts from script-made JSON files (Inventory → Import JSON
  or `--import-products`), one template per part type (docs/product-import.md).
- **Imports**: CSV (generic and Strava export), resumable and repeatable. Strava API: set up, connect, sync
  and disconnect (keeps all rides) from Settings (command line still works), tested against a fake Strava only (docs/strava.md).
- **UI**: Overview, Bikes, Maintenance, Rides, Inventory, Settings; desktop and phone layouts;
  empty/loading/error states; forms keep input after errors; demo mode separate from real data.

## Update an existing Windows build
See [UPDATING.md](UPDATING.md): close the app, `git pull`, rebuild, reinstall. Data is kept.

## Launch (development, from the repository root)
```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt        # Windows: .venv\Scripts\python
cd frontend && npm ci && npm run build && cd ..
cd backend && ../.venv/bin/python -m bikelog                   # opens http://127.0.0.1:8765/
../.venv/bin/python -m bikelog --demo                          # sample data in a separate demo database
```
Options: `--no-browser`, `--port N`, `--data-dir PATH`, `--backup`, `--export`, `--restore FILE`, `--version`.

## Checks actually run (final run on this commit)
| Check | Result |
|---|---|
| Backend tests `pytest -q backend/tests` | 189 passed |
| Required tests: 260 km liquid wax · liquid wax keeps hot wax at 500 km · chain swap · edit/remove/restore once · reimport no duplicates · bleed keeps fluid deadline · DB upgrade keeps records | all pass (test_chain_maintenance, test_rides, test_imports, test_brakes_rules, test_migrations_backup) |
| Dirk's replacement examples (tube, patch, bar tape, rewrap, tire move, pads 3→2 + undo, stock modes) | pass (test_replacement_stock.py, test_api.py) |
| Frontend `tsc -b`, `eslint .`, `vite build` | pass |
| Browser automation `e2e/smoke.cjs` against the real app (desktop 1280×900 and phone 390×844) | 93/93 |
| Sample database `e2e/sample.cjs` (new data dir: banner, sample bikes, crash item, Fresh start removes it) | 5/5 |
| Groupset import: placement, occupied positions, replace, undo, product reuse, every template option | pass (test_groupsets.py) |
| Costs counted once (moves, stock, services, undo) and journal (issues, voiding, no deletes) | pass (test_costs_journal.py) |
| JSON import: templates valid and in sync, all errors listed, idempotent, CLI exit codes | pass (test_product_import.py) |
| Restart persistence (dev server and frozen build) | data identical after a new process |
| Real upgrade 0002→0003 of a database made by the previous version | records kept, pre-upgrade backup written |
| PyInstaller build on Linux, run with a cleared environment | builds, starts, persists, upgrades |

## Packaging status
- Linux: frozen one-folder build verified (see above). Not a deliverable, only proves the recipe.
- **Windows:** Dirk built BikeLog.exe and the installer on his PC on 2026-10-25; installing and the
  checklist are still pending. Build steps and the checklist
  (including which checks need a clean Windows machine without Python) are in `packaging/README.md`.

## Blockers and limitations
- No Windows machine in the build environment.
- Strava: terms not fully read; OAuth never completed against the real Strava (strava.com unreachable from here).
- Groupset template specs not yet checked against Shimano's own documentation.
- Stock line details and compatibility can be set via the API but not yet edited in the UI.
- App is unsigned; Windows SmartScreen will warn.

## Next action for Dirk
1. Get the code: on GitHub open the repository, switch to the branch `claude/project-thread-6y3mmh`,
   then "Code → Download ZIP" (or `git clone` + `git checkout claude/project-thread-6y3mmh`).
2. Either follow `packaging/README.md` to build `BikeLog.exe` on your PC, or ask a local Claude Code
   session to do it (below).
3. Run the Windows checklist and report what fails.
4. Reset the Strava client secret before any Strava work.

## Continuing in a local Claude Code session
Open the cloned folder in Claude Code on Windows and say: "Read HANDOVER.md, DECISIONS.md and
TASKS.md, then build the Windows package per packaging/README.md and work through the Windows
checklist. Do not touch my real data folder except through the app." Everything needed is in the
repository; no database or secrets are.
