# Packaging Bike Log for Windows

**Status (2026-10-24): the build recipe is verified on Linux only. The Windows build, installer,
install, launch and upgrade have NOT been run on Windows yet and are pending.**

What was verified on Linux (x86_64) with the same spec file:
* `pyinstaller packaging/bikelog.spec` builds a one-folder app (48 MB) that bundles Python, the
  backend, the migrations and the built frontend.
* The frozen app starts with a cleared environment (`env -i`), serves the UI and API on 127.0.0.1,
  and keeps data across a real restart (new process, same data folder).
* Opening a database from the previous schema (0002) upgrades it to 0003, writes a pre-upgrade backup
  first, and keeps every record.
* It refuses a data folder inside the install folder.

## Build on Windows (reproducible)

Needs, on the build machine only: Python 3.13 (64-bit), Node.js 22, Git, and optionally Inno Setup 6.

```powershell
git clone https://github.com/dirksachse74/bike_log.git
cd bike_log
git checkout claude/project-thread-6y3mmh
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q backend/tests
cd frontend; npm ci; npm run build; cd ..
.venv\Scripts\pyinstaller --noconfirm --clean packaging\bikelog.spec
# result: dist\BikeLog\BikeLog.exe  (copy the whole dist\BikeLog folder)
# optional installer:
# install once: winget install JRSoftware.InnoSetup  (often lands in your user folder)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\bikelog.iss   # the & is needed in PowerShell
# or, for a machine-wide install: & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\bikelog.iss
# result: dist\installer\BikeLog-0.1.0-setup.exe
```

## Windows verification checklist (all pending)

Building is not testing. Tick these only after doing them.

On the build machine (Python present):
- [ ] `pytest` passes on Windows (paths, file locking, timezone data).
- [ ] PyInstaller build finishes without missing-module warnings that matter.
- [ ] `dist\BikeLog\BikeLog.exe --version` prints `Bike Log 0.1.0 (schema 0005)`.

**Need a clean Windows machine without Python or Node** (a fresh VM or Windows Sandbox):
- [ ] The installer runs without admin rights and installs to `%LOCALAPPDATA%\Programs\BikeLog`.
- [ ] Start menu entry launches the app; the browser opens `http://127.0.0.1:8765/`.
- [ ] Windows Defender / SmartScreen behaviour noted (unsigned app: "More info → Run anyway").
- [ ] Data is created in `%LOCALAPPDATA%\BikeLog` (data, backups, logs), not in the install folder.
- [ ] Add a bike, a chain and a ride; close the window; start again; everything is still there.
- [ ] Starting a second time while running opens the existing app instead of a second copy.
- [ ] `BikeLog.exe --backup` and Settings → Backups create a backup file; `--export` creates a zip.
- [ ] Install this version over an older version (upgrade): data kept, a `pre-upgrade` backup exists.
- [ ] Uninstall removes the program but keeps `%LOCALAPPDATA%\BikeLog`.
- [ ] Demo mode (`BikeLog.exe --demo`) uses `%LOCALAPPDATA%\BikeLog\demo` and never the real database.

## Files
* `entry.py` – PyInstaller entry point (calls `bikelog.launcher.main`).
* `bikelog.spec` – one-folder build; bundles `frontend/dist` as `bikelog/static` and the migrations.
* `bikelog.iss` – Inno Setup per-user installer (written, untested).
* `ci/windows-build.yml.example` – inactive GitHub Actions example; activating it needs your OK.
