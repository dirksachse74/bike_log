# Strava connector status

**Status: implemented and tested against a fake Strava server; never connected live.**
The connector is isolated in `backend/bikelog/connectors/strava/` and disabled unless the
environment variable `BIKELOG_ENABLE_STRAVA=1` is set. The app works fully without it
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

## To try it on your machine later

1. Reset the client secret on strava.com, create `strava.env` in the data folder with
   `STRAVA_CLIENT_ID=...` and `STRAVA_CLIENT_SECRET=...`.
2. There is no button or command for the live connection yet. The building blocks exist
   (`StravaClient.authorize_via_localhost()` and `sync.sync()`); a small command around them is the
   first Strava task in TASKS.md. It needs `BIKELOG_ENABLE_STRAVA=1`.
3. Check the result against your Strava totals before relying on it.
