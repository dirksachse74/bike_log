# Handover

Repository: https://github.com/dirksachse74/bike_log (private) · branch `claude/project-thread-6y3mmh`
State as of 2026-10-24 (latest commit: see `git log -1` on the branch).

## What works (tested in the build environment: Linux x86_64, Python 3.13, Node 22)
- **Bikes, parts, installations**: products vs physical parts, install/remove/replace/move with
  effective dates, conflict protection, lifetime mileage across bikes, chains labelled A/B/C.
- **Rides**: manual rides, edit/exclude/restore with exact-once totals, starting mileage with estimate
  flag, uncertain assignments, "where the kilometres come from" ledger, trainer profile.
- **Maintenance**: hot wax every 500 km, one liquid top-up per 250–300 km window, wear checks,
  brake circuits front/rear independent, bleed vs full fluid replacement, wheel/bearing/freehub rules,
  snooze, explanation for every due task.
- **Spare parts and replacement**: Replace button with preselected bike/position/outgoing part,
  "What happened to the old item?", stock counts per product, install from stock, tube patch and
  return to spares, bar tape rewrap, tire position change and swap, undo of a whole work session,
  shopping list from minimum stock, purchases/returns/corrections, compatibility labels.
- **Imports**: CSV (generic and Strava export), resumable and repeatable. Strava API connector isolated
  and off; never connected live (docs/strava.md).
- **UI**: Overview, Bikes, Maintenance, Rides, Inventory, Settings; desktop and phone layouts;
  empty/loading/error states; forms keep input after errors; demo mode separate from real data.

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
| Backend tests `pytest -q backend/tests` | 81 passed |
| Required tests: 260 km liquid wax · liquid wax keeps hot wax at 500 km · chain swap · edit/remove/restore once · reimport no duplicates · bleed keeps fluid deadline · DB upgrade keeps records | all pass (test_chain_maintenance, test_rides, test_imports, test_brakes_rules, test_migrations_backup) |
| Dirk's replacement examples (tube, patch, bar tape, rewrap, tire move, pads 3→2 + undo, stock modes) | pass (test_replacement_stock.py, test_api.py) |
| Frontend `tsc -b`, `eslint .`, `vite build` | pass |
| Browser automation `e2e/smoke.cjs` against the real app (desktop 1280×900 and phone 390×844) | 31/31 (one earlier run failed once on a timing issue, two reruns passed) |
| Restart persistence (dev server and frozen build) | data identical after a new process |
| Real upgrade 0002→0003 of a database made by the previous version | records kept, pre-upgrade backup written |
| PyInstaller build on Linux, run with a cleared environment | builds, starts, persists, upgrades |

## Packaging status
- Linux: frozen one-folder build verified (see above). Not a deliverable, only proves the recipe.
- **Windows: pending.** Not built, installed or launched on Windows. Build steps and the checklist
  (including which checks need a clean Windows machine without Python) are in `packaging/README.md`.

## Blockers and limitations
- No Windows machine in the build environment.
- Strava: terms not fully read, no credentials, OAuth never completed, strava.com unreachable from here.
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
