"""Manual rides, corrections, exclusion/restore and explicit equipment.

Every change re-allocates only the affected ride (contributions are replaced, never appended), so a
change applied twice has the same effect as applied once. Imported rides keep their source values in
ride_source; local corrections go to ride_override and survive re-imports.
"""
from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES
from bikelog.models import (
    Bike, Component, Ride, RideEquipment, RideFlag, RideOverride, RideSource, UsageContribution, UsageProfile,
)
from bikelog.services import allocation, settings
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import get_bike, get_component
from bikelog.timeutil import parse_when

KM_PER_MILE = 1.609344
EDITABLE_FIELDS = ("name", "when", "distance_km", "duration_s", "bike_id", "sport_type", "usage_profile_code",
                   "assignment_uncertain", "uncertainty_note", "notes")
# fields an import may set; anything in ride_override wins over these
SOURCE_FIELDS = ("name", "when", "distance_km", "duration_s", "bike_id", "sport_type", "usage_profile_code")


def get_ride(session: Session, ride_id: int) -> Ride:
    r = session.get(Ride, ride_id)
    if not r:
        raise NotFound(f"Ride {ride_id} not found")
    return r


def to_km(value: float | None, unit: str = "km") -> float | None:
    if value is None:
        return None
    if value < 0:
        raise DomainError("Distance cannot be negative")
    if unit == "km":
        return float(value)
    if unit == "mi":
        return float(value) * KM_PER_MILE
    raise DomainError("Distance unit must be km or mi")


def profile_id(session: Session, code: str | None) -> int | None:
    if not code:
        return None
    pid = session.scalar(select(UsageProfile.id).where(UsageProfile.code == code))
    if pid is None:
        raise DomainError(f"Unknown usage profile {code!r}")
    return pid


def _default_profile(session: Session, sport_type: str) -> str | None:
    if sport_type == "VirtualRide":
        return settings.get(session, "trainer_profile_for_virtual") or None
    return None


def _apply_fields(session: Session, ride: Ride, values: dict) -> None:
    tz = settings.tz(session)
    if "when" in values:
        w = parse_when(values["when"], tz)
        ride.ride_date = w.local_date
        ride.start_time_utc = None if w.date_only else w.utc
        ride.sort_utc = w.utc
    if "distance_km" in values:
        ride.distance_km = to_km(values["distance_km"]) if values["distance_km"] is not None else None
    if "duration_s" in values:
        d = values["duration_s"]
        if d is not None and d < 0:
            raise DomainError("Duration cannot be negative")
        ride.duration_s = d
    if "bike_id" in values:
        if values["bike_id"] is not None:
            get_bike(session, values["bike_id"])
        ride.bike_id = values["bike_id"]
    if "usage_profile_code" in values:
        ride.usage_profile_id = profile_id(session, values["usage_profile_code"])
    for k in ("name", "sport_type", "uncertainty_note", "notes"):
        if k in values:
            setattr(ride, k, values[k])
    if "assignment_uncertain" in values:
        ride.assignment_uncertain = bool(values["assignment_uncertain"])


def _allocate(session: Session, ride: Ride) -> None:
    session.flush()
    allocation.allocate_rides(session, [ride], settings.tz(session))


def add_manual_ride(session: Session, *, bike_id: int | None, when: str, distance: float | None, unit: str = "km",
                    duration_s: int | None = None, name: str | None = None, sport_type: str = "Ride",
                    usage_profile_code: str | None = None, assignment_uncertain: bool = False,
                    uncertainty_note: str | None = None, notes: str | None = None,
                    equipment: dict[str, int | None] | None = None) -> Ride:
    """Bike + date + distance is enough. Date-only rides get no invented clock time."""
    if bike_id is None and not assignment_uncertain:
        raise DomainError("Pick a bike (or mark the ride as uncertain)")
    ride = Ride(source_kind="MANUAL", sport_type=sport_type or "Ride")
    values = {"when": when, "distance_km": to_km(distance, unit), "duration_s": duration_s, "bike_id": bike_id,
              "name": name, "assignment_uncertain": assignment_uncertain, "uncertainty_note": uncertainty_note,
              "notes": notes, "usage_profile_code": usage_profile_code or _default_profile(session, sport_type)}
    _apply_fields(session, ride, values)
    session.add(ride)
    session.flush()
    for slot, cid in (equipment or {}).items():
        _put_equipment(session, ride, slot, cid)
    _allocate(session, ride)
    return ride


def source_values(session: Session, ride: Ride) -> dict | None:
    src = session.scalar(select(RideSource).where(RideSource.ride_id == ride.id))
    return json.loads(src.values_json) if src else None


def edit_ride(session: Session, ride_id: int, changes: dict) -> Ride:
    ride = get_ride(session, ride_id)
    changes = dict(changes)
    unit = changes.pop("unit", None) or "km"
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise DomainError(f"Cannot edit {', '.join(sorted(unknown))}")
    if changes.get("distance_km") is not None:
        changes["distance_km"] = to_km(changes["distance_km"], unit)
    src = source_values(session, ride)
    if src is not None:
        for field in set(changes) & set(SOURCE_FIELDS):
            new = changes[field]
            if src.get(field) == new:  # back to the source value: drop the override
                session.execute(delete(RideOverride).where(RideOverride.ride_id == ride.id, RideOverride.field == field))
            else:
                ov = session.get(RideOverride, (ride.id, field))
                if ov:
                    ov.value_json = json.dumps(new)
                else:
                    session.add(RideOverride(ride_id=ride.id, field=field, value_json=json.dumps(new)))
    _apply_fields(session, ride, changes)
    _allocate(session, ride)
    return ride


def apply_effective(session: Session, ride: Ride, src: dict) -> None:
    """Effective values = local override if present, else source value."""
    overrides = {o.field: json.loads(o.value_json) for o in session.scalars(
        select(RideOverride).where(RideOverride.ride_id == ride.id))}
    values = {f: overrides.get(f, src.get(f)) for f in SOURCE_FIELDS if f in src or f in overrides}
    _apply_fields(session, ride, values)


def exclude_ride(session: Session, ride_id: int, reason: str | None = None) -> Ride:
    ride = get_ride(session, ride_id)
    if ride.inclusion != "EXCLUDED":
        ride.inclusion = "EXCLUDED"
        ride.exclusion_reason = reason or "removed by user"
        _allocate(session, ride)
    return ride


def restore_ride(session: Session, ride_id: int) -> Ride:
    ride = get_ride(session, ride_id)
    if ride.inclusion != "INCLUDED":
        ride.inclusion = "INCLUDED"
        ride.exclusion_reason = None
        _allocate(session, ride)
    return ride


def _put_equipment(session: Session, ride: Ride, slot: str, component_id: int | None, note: str | None = None) -> None:
    if component_id is not None:
        comp = get_component(session, component_id)
        allowed = COMPONENT_TYPES[comp.component_type].slots
        if allowed and slot not in allowed:
            raise DomainError(f"{comp.label} cannot be used in slot {slot}")
    row = session.get(RideEquipment, (ride.id, slot))
    if row:
        row.component_id, row.note = component_id, note
    else:
        session.add(RideEquipment(ride_id=ride.id, slot=slot, component_id=component_id, note=note))


def set_equipment(session: Session, ride_id: int, slot: str, component_id: int | None, note: str | None = None) -> Ride:
    """Confirm which part (or none) a ride used in a slot. Overrides installation history for that ride."""
    ride = get_ride(session, ride_id)
    _put_equipment(session, ride, slot, component_id, note)
    _allocate(session, ride)
    return ride


def clear_equipment(session: Session, ride_id: int, slot: str) -> Ride:
    ride = get_ride(session, ride_id)
    session.execute(delete(RideEquipment).where(RideEquipment.ride_id == ride.id, RideEquipment.slot == slot))
    _allocate(session, ride)
    return ride


# ---------------------------------------------------------------- reads

def possible_duplicates(session: Session, ride: Ride) -> list[int]:
    if ride.bike_id is None or ride.distance_km is None:
        return []
    pct = float(settings.get(session, "duplicate_window_km_pct")) / 100
    others = session.scalars(select(Ride).where(
        Ride.id != ride.id, Ride.bike_id == ride.bike_id, Ride.ride_date == ride.ride_date,
        Ride.inclusion == "INCLUDED", Ride.status == "ACTIVE", Ride.distance_km.is_not(None)))
    return [o.id for o in others if abs(o.distance_km - ride.distance_km) <= max(0.5, pct * ride.distance_km)]


def ride_row(session: Session, ride: Ride, bikes: dict[int, str] | None = None) -> dict:
    bikes = bikes if bikes is not None else dict(session.execute(select(Bike.id, Bike.name)).all())
    flags = [{"code": f.code, "slot": f.slot, "detail": f.detail}
             for f in session.scalars(select(RideFlag).where(RideFlag.ride_id == ride.id))]
    dups = possible_duplicates(session, ride) if ride.inclusion == "INCLUDED" else []
    if dups:
        flags.append({"code": "POSSIBLE_DUPLICATE", "slot": None,
                      "detail": f"Similar ride on the same day and bike (ride {', '.join(map(str, dups))}). "
                                "Exclude one if it is the same outing."})
    profile = session.get(UsageProfile, ride.usage_profile_id) if ride.usage_profile_id else None
    overridden = list(session.scalars(select(RideOverride.field).where(RideOverride.ride_id == ride.id)))
    return {
        "id": ride.id, "uuid": ride.uuid, "name": ride.name, "ride_date": ride.ride_date,
        "start_time_utc": ride.start_time_utc, "date_only": ride.start_time_utc is None,
        "distance_km": ride.distance_km, "duration_s": ride.duration_s, "sport_type": ride.sport_type,
        "bike_id": ride.bike_id, "bike": bikes.get(ride.bike_id) if ride.bike_id else None,
        "usage_profile": profile.code if profile else None, "usage_profile_name": profile.name if profile else None,
        "source_kind": ride.source_kind, "status": ride.status, "inclusion": ride.inclusion,
        "exclusion_reason": ride.exclusion_reason, "assignment_uncertain": ride.assignment_uncertain,
        "uncertainty_note": ride.uncertainty_note, "notes": ride.notes, "flags": flags,
        "overridden_fields": overridden,
    }


def ride_detail(session: Session, ride: Ride) -> dict:
    row = ride_row(session, ride)
    contribs = session.execute(select(UsageContribution, Component.label, Component.component_type).join(
        Component, Component.id == UsageContribution.component_id).where(UsageContribution.ride_id == ride.id)
        .order_by(UsageContribution.slot)).all()
    row["equipment"] = [{"component_id": c.component_id, "label": label, "component_type": ctype, "slot": c.slot,
                         "km": c.km, "basis": c.basis, "certain": c.certain, "state": c.state, "note": c.note}
                        for c, label, ctype in contribs]
    row["explicit_equipment"] = [{"slot": e.slot, "component_id": e.component_id, "note": e.note}
                                 for e in session.scalars(select(RideEquipment).where(RideEquipment.ride_id == ride.id))]
    row["source_values"] = source_values(session, ride)
    return row


def list_rides(session: Session, *, bike_id: int | None = None, include_excluded: bool = True,
               flagged_only: bool = False, limit: int = 200, offset: int = 0) -> list[dict]:
    q = select(Ride)
    if bike_id is not None:
        q = q.where(Ride.bike_id == bike_id)
    if not include_excluded:
        q = q.where(Ride.inclusion == "INCLUDED")
    q = q.order_by(Ride.sort_utc.desc(), Ride.id.desc()).limit(limit).offset(offset)
    bikes = dict(session.execute(select(Bike.id, Bike.name)).all())
    rows = [ride_row(session, r, bikes) for r in session.scalars(q)]
    if flagged_only:
        rows = [r for r in rows if r["flags"]]
    return rows
