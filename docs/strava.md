# Strava connector status

**Status: implemented and tested against a fake Strava server; first live run pending on Dirk's PC.**
The connector is isolated in `backend/bikelog/connectors/strava/` and runs only through the explicit
commands below (or with `BIKELOG_ENABLE_STRAVA=1` for developers). The app works fully without it
(manual rides and CSV import, including your Strava `activities.csv` export).

## Exact blockers (as of 2026-10-24)

1. **Terms / retention policy** – the 2026 Strava API policy (7-day cache limit, no persistent
   derived data, deletion on revocation) could only be read from search snippets; the full text was not
   reachable. You decided to store API data permanently at your own risk; the code still supports a
   `PROVISIONAL` retention mode and deletes imported rides on disconnect (rides you excluded keep only
   their identity, so they cannot come back).
2. **Credentials** – no Strava API application credentials are configured. They belong in a
   `strava.env` file in your data folder (`%LOCALAPPDATA%\BikeLog\strava.env`) or the path in
   `BIKELOG_STRAVA_ENV`, never in the repository. The client secret pasted in chat earlier must be reset
   on strava.com/settings/api before use.
3. **OAuth** – authorisation has never been completed; it needs a browser on your machine.
4. **Network** – the build environment cannot reach strava.com, so no live call was made.
5. **App capacity** – a new Strava API app starts with athlete capacity 1 (your own account), which is
   enough for personal use.

## What is implemented and tested (tests/test_strava_connector.py)

* Activities listed oldest-first after max(import start date, cursor − 3 days overlap).
* Each page is written in one transaction together with the cursor: resumable, never ahead of the data.
* Identity `(STRAVA, "strava", activity id)` shared with the CSV export.
* Gear ids (`b12345`) mapped to bikes by their Strava gear id; trainer/VirtualRide uses the trainer profile.
* Local corrections and exclusions preserved; rate limits, retries and token refresh in `client.py`.

## How to connect (in the app, no command line)

1. On https://www.strava.com/settings/api: reset the Client Secret (the old one was shared in chat), and
   set **Authorization Callback Domain** to `localhost`.
2. Bike Log → **Settings → Strava**: enter Client ID and Client Secret → **Save app details**. They are
   stored only in `strava.env` in your data folder (`%LOCALAPPDATA%\BikeLog`); the secret is never shown
   again, logged or sent anywhere except to Strava.
3. **Connect with Strava** → Strava opens → **Authorize** → you come back to Settings ("Strava connected").
4. Optional: Settings → Import start date, to limit how far back rides are imported. Bikes are matched by
   Strava gear id, otherwise by gear name (or a bike with that name is created).
5. **Sync now** (a backup is written first; progress shows on the page). Run it whenever you want new
   rides. **Re-read all since start date** re-reads everything (no duplicates).
6. **Disconnect** revokes access and deletes rides imported from the Strava API (backup first).

The command-line versions still work with Bike Log closed: `BikeLog.exe --strava-connect`,
`--strava-sync`, `--strava-rescan`, `--strava-disconnect`.
Tested against a simulated Strava only; the first real connection happens on your machine.
