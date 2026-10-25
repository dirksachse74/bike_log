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

## How to connect (Windows)

Bike Log must be closed while these commands run. In PowerShell, go to the program folder
(`dist\BikeLog` after a build, or `%LOCALAPPDATA%\Programs\BikeLog` after installing).

1. On https://www.strava.com/settings/api: reset the Client Secret (the old one was shared in chat), and
   set **Authorization Callback Domain** to `localhost`.
2. `.\BikeLog.exe --strava-connect` asks once for Client ID and Client Secret (saved only in
   `%LOCALAPPDATA%\BikeLog\strava.env`), opens Strava in the browser; click **Authorize**.
3. Optional: in Bike Log, Settings → Import start date, to limit how far back rides are imported.
   Optional: give your existing bikes their Strava gear id (number from the bike's Strava URL), otherwise
   Bike Log creates or links bikes by the Strava gear name.
4. `.\BikeLog.exe --strava-sync` writes a backup, then imports rides page by page. Run it again whenever
   you want new rides; it continues where it stopped. `--strava-rescan` re-reads everything since the
   start date (no duplicates).
5. `.\BikeLog.exe --strava-disconnect` revokes access and deletes rides imported from the API.

From a source checkout use `python -m bikelog --strava-connect` (in `backend/`) instead of `BikeLog.exe`.
These commands are tested against a fake Strava only; the first real run is on your machine.
