# CSV ride import

Settings → Import (CSV) accepts two formats. Imports are safe to repeat and to resume: each
source row has a unique identity in the database (`ride_source` UNIQUE on source kind, account and
reference), and the cursor is committed together with every chunk of 100 rows.

## 1. Strava "Download your data" export (`activities.csv`)

Recognised by the columns `Activity ID` and `Activity Date`. Only cycling types are imported
(Ride, VirtualRide, GravelRide, MountainBikeRide, EBikeRide); other rows are counted as skipped.
The bike is matched by the `Activity Gear` name against your bike names. This is your own account
export, not Strava API data, and uses the same identity as the API connector, so an activity can
never be counted twice even if both are used.

## 2. Generic CSV

Comma or semicolon separated (semicolon files may use a decimal comma). UTF‑8, header row required.

| Column | Required | Meaning |
|---|---|---|
| `source_id` | yes | Stable unique id of the ride in your source. Re-importing the same id updates instead of duplicating. |
| `date` | yes | `YYYY-MM-DD` (date only) or `YYYY-MM-DDTHH:MM` (local time) or an ISO instant with `Z`. |
| `distance_km` or `distance_mi` | one of them | Distance. Empty means unknown (the ride is kept and flagged). |
| `duration_min` or `duration_s` | no | Moving/elapsed time. |
| `name` | no | Ride name. |
| `bike` | no | Bike name exactly as in Bike Log. Unknown or empty: the ride has no bike and is flagged. |
| `sport_type` | no | Default `Ride`. `VirtualRide` uses the trainer profile. |
| `trainer` | no | `yes/true/1` uses the trainer profile (removed wheels/tires/pads get no km). |

Template (also downloadable in the app):

```csv
source_id,date,distance_km,duration_min,name,bike,sport_type,trainer
garmin-2026-10-05-1,2026-10-05,62.4,128,Taunus loop,TIME NXR,Ride,no
zwift-2026-10-07,2026-10-07T18:30,35.0,60,Zwift race,TIME NXR,VirtualRide,yes
```

## Rules

* **Start date**: Settings → Import start date. Rows before it are skipped (`SKIPPED_BEFORE_START`).
* **Local corrections win**: fields you edited in Bike Log are stored as overrides; a re-import updates
  the source values but keeps your corrections.
* **Excluded rides stay excluded**: imports never change inclusion, so a ride you excluded does not
  silently return.
* **Retry/resume**: importing the same file again resumes an unfinished batch or reports rows as
  unchanged. Row errors are listed with their row number; good rows are still imported.
