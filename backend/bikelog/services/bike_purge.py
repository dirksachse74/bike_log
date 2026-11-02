"""Delete a bike for good (Dirk 2026-11-02, DECISIONS 128).

Dirk: "i want the option to perma delete bikes. i dont want to see irrelevant bikes in the overview".

The database keeps history append-only on purpose (maintenance, notes and the change log cannot be deleted,
a bike with rides cannot be deleted; database triggers). So a deleted bike is not wiped from the file: it is
taken out of the app for good.

* The API takes a backup first that is never pruned ("kept-before-bike-delete"); Settings → Backups →
  Restore is the only way back.
* The bike gets ``deleted_at`` and status RETIRED, and its name is freed ("Old bike (deleted 2026-11-02)").
  It is in no list, picker or overview any more, not even under Retired.
* Its rides are removed (count no km) and are not listed anywhere; rides from Strava or a CSV file are
  therefore never imported again, and the bike's Strava gear is ignored from now on.
* Parts are never deleted. They come off the bike into storage (or retired with ``retire_parts``) and keep
  the km they rode on it as one correction "km on <bike> (bike deleted …)".
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.models import Bike, Component, Installation, JournalEntry, MaintenanceEvent, Ride, UsageContribution
from bikelog.services import inventory as inv
from bikelog.services import settings
from bikelog.services.errors import DomainError
from bikelog.timeutil import today_local, utc_now


def deleted_ids(session: Session) -> set[int]:
    return set(session.scalars(select(Bike.id).where(Bike.deleted_at.is_not(None))))


def preview(session: Session, bike_id: int) -> dict:
    """What a delete takes with it, for the confirm sheet."""
    bike = inv.get_bike(session, bike_id)
    rides = list(session.scalars(select(Ride).where(Ride.bike_id == bike.id)))
    return {"name": bike.name,
            "rides": len(rides),
            "rides_km": round(sum(r.distance_km or 0 for r in rides if r.inclusion == "INCLUDED"), 1),
            "imported_rides": sum(1 for r in rides if r.source_kind != "MANUAL"),
            "parts": [{"id": c.id, "label": c.label, "km_on_bike": round(k, 1)} for c, k in _parts(session, bike.id)],
            "maintenance": session.scalar(select(func.count()).select_from(MaintenanceEvent).where(
                MaintenanceEvent.bike_id == bike.id, MaintenanceEvent.voided_at.is_(None))) or 0,
            "notes": session.scalar(select(func.count()).select_from(JournalEntry).where(
                JournalEntry.bike_id == bike.id, JournalEntry.voided_at.is_(None))) or 0}


def _parts(session: Session, bike_id: int) -> list[tuple[Component, float]]:
    """Every part that rode on this bike (also a tire on a wheel), with the km it did on it."""
    km: dict[int, float] = defaultdict(float)
    for cid, k in session.execute(select(UsageContribution.component_id, UsageContribution.km).where(
            UsageContribution.bike_id == bike_id, UsageContribution.state == "COUNTED")):
        km[cid] += k or 0
    on_bike = set(session.scalars(select(Installation.component_id).where(
        Installation.bike_id == bike_id, Installation.voided_at.is_(None))))
    ids = set(km) | on_bike
    comps = session.scalars(select(Component).where(Component.id.in_(ids))) if ids else []
    return sorted(((c, km.get(c.id, 0.0)) for c in comps), key=lambda x: x[0].label.lower())


def purge(session: Session, bike_id: int, *, confirm_name: str, retire_parts: bool = False) -> dict:
    bike = inv.get_bike(session, bike_id)
    if bike.deleted_at:
        raise DomainError(f"{bike.name} is already deleted")
    if (confirm_name or "").strip().lower() != bike.name.strip().lower():
        raise DomainError(f'Type the bike\'s name "{bike.name}" to delete it for good.')
    name, today = bike.name, today_local(settings.tz(session)).isoformat()
    parts = _parts(session, bike.id)
    if bike.strava_gear_id:
        ignored = set(json.loads(settings.get(session, "strava_ignored_gear") or "[]"))
        ignored.add(bike.strava_gear_id)
        settings.set_value(session, "strava_ignored_gear", json.dumps(sorted(ignored)), internal=True)

    # rides: removed (no km, never imported again) and listed nowhere
    rides = list(session.scalars(select(Ride).where(Ride.bike_id == bike.id)))
    for r in rides:
        if r.inclusion != "EXCLUDED":
            r.inclusion, r.exclusion_reason = "EXCLUDED", f"bike {name} deleted"
    session.flush()
    inv._reallocate(session)

    # parts: off the bike now, keeping the km they rode on it
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in list(session.scalars(select(Installation).where(
            Installation.bike_id == bike.id, Installation.removed_utc.is_(None), Installation.voided_at.is_(None)))):
        inv.remove(session, i.component_id, at=now, reason=f"{name} deleted",
                   outcome="RETIRED" if retire_parts else "STORED", reallocate=False)
    for c, k in parts:
        if k > 0:
            inv.add_correction(session, c.id, round(k, 3), today, f"km on {name} (bike deleted {today})")
    session.query(Component).filter(Component.rotation_bike_id == bike.id).update({"rotation_bike_id": None})

    bike.deleted_at = utc_now()
    bike.status = "RETIRED"
    bike.strava_gear_id = None
    bike.name = f"{name} (deleted {today})"
    n = 2
    while session.scalar(select(Bike.id).where(Bike.name == bike.name, Bike.id != bike.id)):
        bike.name = f"{name} (deleted {today}, {n})"
        n += 1
    session.flush()
    inv._reallocate(session)
    return {"name": name, "rides": len(rides), "parts": len(parts), "parts_retired": retire_parts}
