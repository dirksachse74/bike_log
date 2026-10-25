# Updating Bike Log on Windows (git pull and rebuild)

Use this every time new changes were pushed to the branch `claude/project-thread-6y3mmh`.
It assumes you already built Bike Log once on this PC (see `packaging/README.md`), in
`D:\Ablage\Coding\bike_log`. All commands are for **PowerShell**. Your data is never touched by
these steps: it lives in `%LOCALAPPDATA%\BikeLog`, not in the code folder or the install folder.

## Short version

```powershell
cd D:\Ablage\Coding\bike_log
git fetch origin
git checkout claude/project-thread-6y3mmh
git pull origin claude/project-thread-6y3mmh
.venv\Scripts\python -m pip install -r requirements-dev.txt
cd frontend; npm ci; npm run build; cd ..
.venv\Scripts\pyinstaller --noconfirm --clean packaging\bikelog.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\bikelog.iss
```

Then close Bike Log, run `dist\installer\BikeLog-0.1.0-setup.exe`, and start Bike Log again.

## Step by step

1. **Close Bike Log.** Close its black console window (closing it stops the app). If you are not sure
   it is closed, open Task Manager and end `BikeLog.exe`. The build would otherwise fail because files
   in `dist\BikeLog` are in use.

2. **Get the new code.**
   ```powershell
   cd D:\Ablage\Coding\bike_log
   git status
   ```
   `git status` should say "nothing to commit, working tree clean". If it lists files you changed and
   you do not need those changes, run `git restore .` to throw them away (this only affects the code
   folder, never your Bike Log data). Then:
   ```powershell
   git fetch origin
   git checkout claude/project-thread-6y3mmh
   git pull origin claude/project-thread-6y3mmh
   git log -1 --oneline
   ```
   `fetch` downloads what is new, `checkout` makes sure you are on the right branch, `pull` brings your
   folder up to date. `git log -1 --oneline` shows the newest commit; it should match the one named in
   the last message from Claude.

3. **Update the Python packages** (only installs what changed, safe to run every time):
   ```powershell
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

4. **Build the screens (frontend).**
   ```powershell
   cd frontend; npm ci; npm run build; cd ..
   ```
   `npm ci` installs exactly the versions in `package-lock.json`; `npm run build` writes `frontend\dist`.

5. **Optional: run the tests** (about a minute; tells you the update works on Windows too):
   ```powershell
   .venv\Scripts\python -m pytest -q backend/tests
   ```

6. **Build BikeLog.exe.**
   ```powershell
   .venv\Scripts\pyinstaller --noconfirm --clean packaging\bikelog.spec
   ```
   Result: `dist\BikeLog\BikeLog.exe`. You can start this directly to try the new version.

7. **Build and run the installer** (if you installed Bike Log with the installer):
   ```powershell
   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\bikelog.iss
   ```
   The `&` is needed in PowerShell before a quoted program path. Then run
   `dist\installer\BikeLog-0.1.0-setup.exe` and install over the old version. No uninstall is needed.

8. **Start Bike Log** from the Start menu. If the new version changes the database, it first writes a
   backup (`%LOCALAPPDATA%\BikeLog\backups\...pre-upgrade...`) and then upgrades. Nothing is deleted.

## Check which version you are running

```powershell
& "$env:LOCALAPPDATA\Programs\BikeLog\BikeLog.exe" --version     # installed copy
dist\BikeLog\BikeLog.exe --version                               # freshly built copy
```
It prints e.g. `Bike Log 0.1.0 (schema 0005)`. The app version number is not raised for every change,
so `git log -1 --oneline` in the code folder is the exact way to see which commit you built.

## If you downloaded a ZIP instead of cloning

A ZIP from GitHub cannot be updated with `git pull`. Either download the new ZIP for the branch and
unpack it into a **new** folder (then run steps 3 to 8 there, after creating `.venv` as in
`packaging/README.md`), or switch to git once:
```powershell
cd D:\Ablage\Coding
git clone https://github.com/dirksachse74/bike_log.git bike_log_git
cd bike_log_git
git checkout claude/project-thread-6y3mmh
py -3.13 -m venv .venv
```
and use that folder from now on. The repository is private, so git asks you to sign in to GitHub
the first time.

## Common problems

| What you see | What to do |
|---|---|
| `git pull` says "Your local changes would be overwritten" | `git restore .` (discards code edits, not data), then pull again. |
| `git pull` says "not a git repository" | You are in the wrong folder or used a ZIP; see above. |
| `ISCC.exe is not recognized` or a red error about the path | Put `&` before the quoted path, check Inno Setup is in `%LOCALAPPDATA%\Programs\Inno Setup 6` (or `C:\Program Files (x86)\Inno Setup 6`). |
| PyInstaller: "Access is denied" / "file in use" in `dist\BikeLog` | Bike Log is still running: close it (step 1) and build again. |
| `npm ci` fails with EPERM or "file in use" | Close editors/terminals using `frontend\node_modules`, try again. |
| The app still looks old in the browser | Press Ctrl+F5 on the Bike Log page to reload without cache. |
| Bike Log says the database is newer than the app | You started an older build. Build/install the newest one. |
| Something is wrong after an update | Your data before the upgrade is in `%LOCALAPPDATA%\BikeLog\backups`. Tell Claude what you saw before restoring anything. |
