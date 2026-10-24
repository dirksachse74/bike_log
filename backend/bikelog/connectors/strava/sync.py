"""Strava API → Bike Log import pipeline (isolated connector, disabled by default).

Enabled only when BIKELOG_ENABLE_STRAVA=1. Reasons and the exact blockers are in DECISIONS.md:
the 2026 API terms (7-day cache, no persistent derived data) could not be verified from the
build environment, and strava.com is unreachable there, so no live connection was ever made.

Behaviour (tested against tests/fake_strava.py):
* lists /athlete/activities oldest-first after max(import start date, cursor - overlap),
* each page is written in one transaction together with the cursor (resumable, never ahead of data),
* identity (STRAVA, "strava", activity id) is the same as for the Strava export CSV, so both
  sources can never double-count one activity,
* local corrections and exclusions are kept (shared pipeline in services/imports.py),
* rate limits / retries / token refresh are handled in client.py.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bikelog.catalog import RIDE_SPORT_TYPES
from bikelog.connectors.strava.client import StravaClient
from bikelog.models import RideSource, StravaConnection
from bikelog.services import imports, settings
from bikelog.timeutil import utc_now

SOURCE_KIND, SOURCE_ACCOUNT = "STRAVA", "strava"
OVERLAP_S = 3 * 24 * 3600

BLOCKERS = [
    "Strava API terms (2026 policy: 7-day cache limit, no persistent derived data) were only seen in search "
    "snippets; the full text could not be read, so permanent storage of API data is unverified.",
    "No Strava API application credentials are configured on this machine (strava.env).",
    "OAuth authorisation has never been completed (needs a browser on your machine).",
    "The build environment cannot reach strava.com, so no live call was ever made.",
]


def enabled() -> bool:
    return os.environ.get("BIKELOG_ENABLE_STRAVA") == "1"


def status(session: Session) -> dict:
    conn = session.get(StravaConnection, SOURCE_ACCOUNT)
    return {"enabled": enabled(), "connected": bool(conn and conn.status == "ACTIVE"),
            "status": conn.status if conn else "NOT_CONNECTED", "last_success_at": conn.last_success_at if conn else None,
            "last_error": conn.last_error if conn else None,
            "retention_mode": conn.retention_mode if conn else "PROVISIONAL",
            "live_connection_verified": False, "blockers": BLOCKERS,
            "alternative": "Import your Strava 'Download your data' activities.csv under Settings → Import (CSV)."}


def _start_epoch(session: Session) -> int:
    start = settings.get(session, "import_start_date") or "2000-01-01"
    tz = ZoneInfo(settings.tz(session))
    d = datetime.fromisoformat(start).replace(tzinfo=tz)
    return int(d.timestamp()) - 1


def _values(session: Session, act: dict) -> dict:
    sport = act.get("sport_type") or act.get("type") or "Ride"
    trainer = bool(act.get("trainer")) or sport == "VirtualRide"
    return {"when": act["start_date"], "distance_km": (act["distance"] / 1000) if act.get("distance") is not None else None,
            "duration_s": act.get("elapsed_time"), "name": act.get("name"), "sport_type": sport,
            "bike_id": imports.resolve_bike(session, gear_id=_gear(act.get("gear_id"))),
            "usage_profile_code": (settings.get(session, "trainer_profile_for_virtual") or None) if trainer else None}


def _gear(gear_id: str | None) -> str | None:
    # Strava bike gear ids look like "b13071041"; bikes store the numeric part (as shown in the Strava UI)
    if gear_id and gear_id.startswith("b"):
        return gear_id[1:]
    return gear_id


def sync(factory: sessionmaker[Session], client: StravaClient, *, rescan: bool = False, per_page: int = 100,
         force: bool = False) -> dict:
    if not (enabled() or force):
        raise RuntimeError("Strava connector is disabled (set BIKELOG_ENABLE_STRAVA=1). See DECISIONS.md.")
    counts: dict[str, int] = {}
    with factory() as s, s.begin():
        conn = s.get(StravaConnection, SOURCE_ACCOUNT)
        if conn is None:
            conn = StravaConnection(athlete_id=SOURCE_ACCOUNT, status="ACTIVE")
            s.add(conn)
        if conn.status == "PAUSED":
            return {"skipped": "paused"}
        conn.status = "ACTIVE"
        after = _start_epoch(s)
        if conn.cursor_epoch and not rescan:
            after = max(after, conn.cursor_epoch - OVERLAP_S)
    try:
        for _page, items in client.iter_activity_pages(after, per_page=per_page):
            with factory() as s, s.begin():
                newest = None
                for act in sorted(items, key=lambda a: a["start_date"]):
                    sport = act.get("sport_type") or act.get("type")
                    if sport not in RIDE_SPORT_TYPES:
                        counts["SKIPPED_NOT_CYCLING"] = counts.get("SKIPPED_NOT_CYCLING", 0) + 1
                        continue
                    res = imports.upsert_record(s, source_kind=SOURCE_KIND, source_account=SOURCE_ACCOUNT,
                                                source_ref=str(act["id"]), values=_values(s, act))
                    counts[res] = counts.get(res, 0) + 1
                    newest = act["start_date"]
                conn = s.get(StravaConnection, SOURCE_ACCOUNT)
                if newest:
                    epoch = int(datetime.fromisoformat(newest.replace("Z", "+00:00")).timestamp())
                    conn.cursor_epoch = max(conn.cursor_epoch or 0, epoch)
    except Exception as e:
        with factory() as s, s.begin():
            conn = s.get(StravaConnection, SOURCE_ACCOUNT)
            conn.last_error = f"{type(e).__name__}: {e}"[:500]
        raise
    with factory() as s, s.begin():
        conn = s.get(StravaConnection, SOURCE_ACCOUNT)
        conn.last_success_at, conn.last_error = utc_now(), None
    return {"counts": counts}


def delete_imported(factory: sessionmaker[Session]) -> dict:
    """On disconnect: delete every Strava-sourced ride and the usage it produced (Strava terms require
    deletion after revocation). Rides you excluded keep only their identity, so they cannot return."""
    from sqlalchemy import delete

    from bikelog.models import Ride, RideEquipment, RideFlag, RideOverride, UsageContribution
    deleted = kept = 0
    with factory() as s, s.begin():
        for src in list(s.scalars(select(RideSource).where(RideSource.source_kind == SOURCE_KIND))):
            ride = s.get(Ride, src.ride_id)
            for model in (UsageContribution, RideFlag, RideOverride, RideEquipment):
                s.execute(delete(model).where(model.ride_id == ride.id))
            if ride.inclusion == "EXCLUDED":
                src.values_json, src.payload_hash = "{}", "deleted"
                ride.name = ride.notes = None
                ride.status = "SOURCE_DELETED"
                kept += 1
            else:
                s.delete(src)
                s.flush()
                s.delete(ride)
                deleted += 1
        conn = s.get(StravaConnection, SOURCE_ACCOUNT)
        if conn:
            conn.status, conn.cursor_epoch = "DISCONNECTED", None
    return {"deleted_rides": deleted, "kept_exclusion_identities": kept}
