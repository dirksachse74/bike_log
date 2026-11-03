# Updating Bike Log on Windows (git pull and rebuild)

Use this every time new changes were pushed to the branch `claude/project-thread-6y3mmh`.
It assumes you already built Bike Log once on this PC (see `packaging/README.md`), in
`D:\Ablage\Coding\bike_log`. All commands are for **PowerShell**. Your data is never touched by
these steps: it lives in `%LOCALAPPDATA%\BikeLog`, not in the code folder or the install folder.

## Easiest: one command

Close Bike Log first, then in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Ablage\Coding\bike_log\packaging\build.ps1
```

It pulls the newest code, installs packages, runs the tests, builds the screens, BikeLog.exe and the
installer, and **stops at the first error** with the step that failed. At the end it prints the
installer's full path: `dist\installer\BikeLog-0.2.0-setup.exe` for a release, or
`BikeLog-0.2.0+abc1234-setup.exe` for a build between releases (the part after `+` is the commit). Every
build has its own name, so an old installer can no longer be mistaken for a new one (see "Versions" below). Options: `-Install` (runs the installer at the end), `-SkipTests`, `-NoPull`.
(`-ExecutionPolicy Bypass` only applies to this one run; Windows blocks unsigned scripts otherwise.)

The script was checked for syntax but not yet run on Windows; if a step fails, send the red line.

## Short version (by hand)

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

Then close Bike Log, run the newest installer in `dist\installer\` (named after the version, see
"Versions" below), and start Bike Log again. Old installers named `BikeLog-0.1.0-setup.exe` or
`BikeLog-0.1.0-<commit>-setup.exe` are from before versioning and can be deleted.

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
   the newest installer in `dist\installer\` and install over the old version. No uninstall is needed.

8. **Start Bike Log** from the Start menu. If the new version changes the database, it first writes a
   backup (`%LOCALAPPDATA%\BikeLog\backups\...pre-upgrade...`) and then upgrades. Nothing is deleted.

## Bike Log on your own server

If Bike Log runs on your server (deploy/README.md), it updates itself every night from `main` when you
chose that during setup; otherwise connect with `ssh root@<server ip>` and type `bikelog-update`.

## Check which version you are running

```powershell
& "$env:LOCALAPPDATA\Programs\BikeLog\BikeLog.exe" --version     # installed copy
dist\BikeLog\BikeLog.exe --version                               # freshly built copy
```
It prints e.g. `Bike Log 0.2.0 (schema 0009, commit 1a2b3c4)`. The commit must match what
`git log -1 --oneline` shows in the code folder (the first 7 characters).

Inside the app: the version is next to the logo (`v0.2.0`, with a `+` for a build between releases), and
**Settings → bottom of "Backups and export"** shows the full version, the database schema, the **app
commit** and the **screens commit**. In Windows, right-click `BikeLog.exe` → Properties → Details shows
the version too. All of them should be the newest commit. If the screens are older than
the app, or the browser still shows old screens, a red bar at the top of every page says so and what to do.

From this update on, the build refuses to start if `frontend\dist` was built from older code, so
forgetting `npm run build` is caught at step 6.

## Versions

Bike Log uses version numbers like **0.2.0** (MAJOR.MINOR.PATCH):
* PATCH (0.2.**1**): only fixes.
* MINOR (0.**3**.0): new features.
* MAJOR (**1**.0.0): a big change, for example to how data is stored.

A **release** is a version that was finished and given its number on purpose (a git tag `v0.2.0` marks
it). Building exactly that state gives `Bike Log 0.2.0` and `BikeLog-0.2.0-setup.exe`. When more changes
come in afterwards, builds show `0.2.0+abc1234` until the next release: "0.2.0 plus the changes up to
commit abc1234". What changed in each version is in [CHANGELOG.md](CHANGELOG.md).

## Making a release

You can simply ask Claude: "make release 0.3.0" (or "a patch release"). To do it yourself, in the code
folder with Bike Log's changes committed:

```powershell
.venv\Scripts\python scripts\release.py minor --dry-run   # shows the new number and the changes
.venv\Scripts\python scripts\release.py minor --push      # does it: patch / minor / major
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -NoPull
```

The script raises the number, dates the "Unreleased" part of CHANGELOG.md, commits "Release 0.3.0",
tags it `v0.3.0` and (with `--push`) pushes the branch and the tag. It refuses on `main`, with uncommitted
changes, or when CHANGELOG.md lists nothing new. The build then makes `BikeLog-0.3.0-setup.exe`.

## Publishing a release for friends (GitHub Releases)

A GitHub machine with Windows builds the installer, tests it (install, start, update over it, data still
there) and puts it on a release page: one download link. Nothing to install or type on your PC.

1. Make the release first, so the version number is raised and the changelog dated: ask Claude for
   "a patch release" / "a minor release" (or run `scripts\release.py`, see above), and let it be merged.
2. On github.com open the repository → **Actions** → **Release (Windows installer)** (left) →
   **Run workflow** → branch `main` → keep **Publish** ticked → **Run workflow**.
3. Wait about 10–15 minutes until the run shows a green tick. A red cross means a step failed; it did not
   publish anything. Click it to see the step, or tell Claude.
4. The release page is **Releases** (right side of the repository's start page). The file
   `BikeLog-X.Y.Z-setup.exe` is under **Assets**. The link
   `https://github.com/<repository>/releases/latest` always points at the newest one.

Pushing a tag `vX.Y.Z` (`scripts\release.py --push`) starts the same build by itself. Running it twice
for the same version replaces the installer of that release. Publishing refuses a version that was already released from
another commit ("Tag vX.Y.Z already exists on another commit"): make a new release first (step 1). Untick **Publish** for a test build: the
installer is then only on the run page (under Artifacts, 7 days), nothing is published.

**Who can download:** a release of a *private* repository is only visible to people with access to the
repository. Friends need either a public repository, a separate public "releases" repository (set the
repository variable `RELEASES_REPO` to e.g. `dirksachse74/bike_log-releases` and the secret
`RELEASES_TOKEN` to a fine-grained token with "Contents: Read and write" on that repository; the code stays
private), or you download the file yourself and send it to them. Friends read
[docs/INSTALL.md](docs/INSTALL.md); its text is also on every release page.

Uses GitHub Actions minutes: a run takes about 10–15 minutes on Windows, which counts double on a private
repository (free plan: 2000 minutes a month).

## Starting over with an empty database

Settings → **Fresh start**: type `RESET` and press **Reset database**. Bike Log first writes a full backup
(its path is shown; the name ends in `kept-before-reset.db`, and it is never deleted automatically), then
starts with an empty database. Strava stays connected unless you tick "Also clear the Strava connection";
press **Sync** in the Strava section to import your rides again. Changed your mind? Press **Undo** right
there, or **Restore** next to that backup under "Backups and export". Updating or reinstalling the app
never resets your data; only this button does.

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
| The app still looks old in the browser (e.g. Settings → Strava shows only "Not connected" and a list of reasons, no fields) | An old Bike Log is still running: starting the new one only opens the old one. Close every Bike Log window, check Task Manager for `BikeLog.exe` and end it, then start Bike Log again. The console window now warns when the running copy is a different version. If it persists, check the commits (above) and press Ctrl+F5. |
| PyInstaller stops with "frontend/dist was built from …" | Run `cd frontend; npm ci; npm run build; cd ..` and build again. |
| Bike Log says the database is newer than the app | You started an older build. Build/install the newest one. |
| Something is wrong after an update | Your data before the upgrade is in `%LOCALAPPDATA%\BikeLog\backups`. Tell Claude what you saw before restoring anything. |
