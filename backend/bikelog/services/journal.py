"""Journal: dated free-text notes on a bike or a part, such as an issue noticed on a ride.

One place for notes: the journal of a part also shows the notes written on its maintenance entries
(symptom, work done, notes), and a bike's journal shows the entries of the parts that were on it.
Maintenance rows are shown read-only; they are edited where they were logged.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS, INCIDENT_TYPES
from bikelog.models import Component, JournalEntry, MaintenanceEvent, Ride
from bikelog.services import settings
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import get_bike, get_component, location
from bikelog.timeutil import parse_when, utc_now

KINDS = {"NOTE": "Note", "ISSUE": "Issue"}


def _date(session: Session, value: str) -> str:
    return parse_when(value, settings.tz(session)).local_date


def add(session: Session, *, text: str | None, on: str | None = None, bike_id: int | None = None,
        component_id: int | None = None, kind: str | None = None, resolved_on: str | None = None,
        ride_id: int | None = None, incident_type: str | None = None) -> JournalEntry:
    """A note or issue. With ``incident_type`` it is an incident (an issue, e.g. a flat on a ride);
    with ``ride_id`` it is linked to that ride: date and bike default to the ride's."""
    ride = None
    if ride_id is not None:
        ride = session.get(Ride, ride_id)
        if ride is None:
            raise NotFound("Ride not found")
        on = on or ride.ride_date
        if bike_id is None and component_id is None:
            bike_id = ride.bike_id
            if bike_id is None:
                raise DomainError("This ride has no bike; pick the bike or the part that was affected")
    if incident_type is not None:
        if incident_type not in INCIDENT_TYPES:
            raise DomainError(f"incident_type must be one of {', '.join(INCIDENT_TYPES)}")
        kind = "ISSUE"
    kind = kind or "NOTE"
    text = (text or "").strip() or (INCIDENT_TYPES[incident_type] if incident_type else "")
    if not text:
        raise DomainError("Write something in the note")
    if not on:
        raise DomainError("Give the date")
    if kind not in KINDS:
        raise DomainError(f"kind must be one of {', '.join(KINDS)}")
    if component_id is not None:
        comp = get_component(session, component_id)
        if bike_id is None:
            bike_id = (ride.bike_id if ride is not None else None) or location(session, comp).get("bike_id")
    elif bike_id is not None:
        get_bike(session, bike_id)
    else:
        raise DomainError("A journal entry belongs to a bike or a part")
    e = JournalEntry(bike_id=bike_id, component_id=component_id, entry_on=_date(session, on), kind=kind, text=text,
                     resolved_on=_date(session, resolved_on) if resolved_on and kind == "ISSUE" else None,
                     ride_id=ride_id, incident_type=incident_type)
    session.add(e)
    session.flush()
    return e


def get(session: Session, entry_id: int) -> JournalEntry:
    e = session.get(JournalEntry, entry_id)
    if not e:
        raise NotFound("Journal entry not found")
    return e


def update(session: Session, entry_id: int, **fields) -> JournalEntry:
    e = get(session, entry_id)
    if e.voided_at:
        raise DomainError("This entry was removed; it can no longer be edited")
    if "text" in fields:
        text = (fields["text"] or "").strip()
        if not text:
            raise DomainError("Write something in the note")
        e.text = text
    if fields.get("on"):
        e.entry_on = _date(session, fields["on"])
    if "kind" in fields and fields["kind"]:
        if fields["kind"] not in KINDS:
            raise DomainError(f"kind must be one of {', '.join(KINDS)}")
        e.kind = fields["kind"]
    if "incident_type" in fields:
        if fields["incident_type"] is not None and fields["incident_type"] not in INCIDENT_TYPES:
            raise DomainError(f"incident_type must be one of {', '.join(INCIDENT_TYPES)}")
        e.incident_type = fields["incident_type"]
        if e.incident_type:
            e.kind = "ISSUE"
    if "resolved_on" in fields:
        e.resolved_on = _date(session, fields["resolved_on"]) if fields["resolved_on"] else None
    if e.kind != "ISSUE":
        e.resolved_on = None
    if "text" in fields or "on" in fields:   # resolving an issue is not an edit of the note
        e.updated_at = utc_now()
    session.flush()
    return e


def void(session: Session, entry_id: int, reason: str | None = None) -> JournalEntry:
    e = get(session, entry_id)
    if not e.voided_at:
        e.voided_at, e.void_reason = utc_now(), reason or "removed"
        session.flush()
    return e


def _ride_label(ride: Ride | None) -> str | None:
    if ride is None:
        return None
    dist = f", {ride.distance_km:,.0f} km" if ride.distance_km is not None else ""
    return f"{ride.name or 'Ride'} ({ride.ride_date}{dist})"


def row(session: Session, e: JournalEntry) -> dict:
    from bikelog.models import Bike
    comp = session.get(Component, e.component_id) if e.component_id else None
    ride = session.get(Ride, e.ride_id) if e.ride_id else None
    bike = session.get(Bike, e.bike_id) if e.bike_id else None
    return {"id": e.id, "source": "JOURNAL", "on": e.entry_on, "kind": e.kind, "text": e.text,
            "resolved_on": e.resolved_on, "open_issue": e.kind == "ISSUE" and not e.resolved_on,
            "bike_id": e.bike_id, "bike": bike.name if bike else None, "component_id": e.component_id,
            "component_label": comp.label if comp else None,
            "component_type": comp.component_type if comp else None,
            "ride_id": e.ride_id, "ride_label": _ride_label(ride), "ride_conditions": ride.conditions if ride else None,
            "incident_type": e.incident_type,
            "incident_label": INCIDENT_TYPES.get(e.incident_type) if e.incident_type else None,
            "edited": bool(e.updated_at), "voided": bool(e.voided_at)}


def _event_row(session: Session, ev: MaintenanceEvent) -> dict | None:
    parts = [p for p in (ev.symptom and f"Symptom: {ev.symptom}", ev.work_done and f"Work done: {ev.work_done}",
                         ev.notes) if p]
    if not parts:
        return None
    comp = session.get(Component, ev.component_id) if ev.component_id else None
    action = ACTIONS[ev.action_code].name if ev.action_code in ACTIONS else ev.action_code
    return {"id": ev.id, "source": "MAINTENANCE", "on": ev.performed_on, "kind": "MAINTENANCE",
            "text": f"{action}: " + " · ".join(parts) + (f" → {ev.outcome.replace('_', ' ').lower()}" if ev.outcome else ""),
            "resolved_on": None, "open_issue": False, "bike_id": ev.bike_id, "bike": None,
            "component_id": ev.component_id, "component_label": comp.label if comp else None,
            "component_type": comp.component_type if comp else None, "ride_id": None, "ride_label": None,
            "ride_conditions": None, "incident_type": None, "incident_label": None, "edited": False, "voided": False}


def entries(session: Session, *, bike_id: int | None = None, component_id: int | None = None,
            ride_id: int | None = None, include_voided: bool = False, include_maintenance: bool = True) -> list[dict]:
    if ride_id is not None:
        q = select(JournalEntry).where(JournalEntry.ride_id == ride_id)
        if not include_voided:
            q = q.where(JournalEntry.voided_at.is_(None))
        return sorted((row(session, e) for e in session.scalars(q)), key=lambda r: r["id"], reverse=True)
    if (bike_id is None) == (component_id is None):
        raise DomainError("Show the journal of one bike or one part")
    target = (JournalEntry.bike_id == bike_id) if bike_id is not None else (JournalEntry.component_id == component_id)
    q = select(JournalEntry).where(target)
    if not include_voided:
        q = q.where(JournalEntry.voided_at.is_(None))
    rows = [row(session, e) for e in session.scalars(q)]
    if component_id is not None:      # entries on parts that were mounted on this one then (wheelset → tire)
        rows += [{**row(session, e), "via_child": True} for e in _entries_below(session, component_id, include_voided)]
    if include_maintenance:
        etarget = (MaintenanceEvent.bike_id == bike_id) if bike_id is not None else (
            MaintenanceEvent.component_id == component_id)
        for ev in session.scalars(select(MaintenanceEvent).where(etarget, MaintenanceEvent.voided_at.is_(None),
                                                                  or_(MaintenanceEvent.symptom.is_not(None),
                                                                      MaintenanceEvent.work_done.is_not(None),
                                                                      MaintenanceEvent.notes.is_not(None)))):
            r = _event_row(session, ev)
            if r:
                rows.append(r)
    rows.sort(key=lambda r: (r["on"], r["source"] == "JOURNAL", r["id"]), reverse=True)
    return rows


def incidents(session: Session, *, bike_id: int | None = None, component_id: int | None = None,
              incident_type: str | None = None, open_only: bool = False) -> list[dict]:
    """All incidents (flats, crashes, defects), newest first, for the Incidents list."""
    q = select(JournalEntry).where(JournalEntry.incident_type.is_not(None), JournalEntry.voided_at.is_(None))
    if bike_id is not None:
        q = q.where(JournalEntry.bike_id == bike_id)
    if component_id is not None:
        q = q.where(JournalEntry.component_id == component_id)
    if incident_type:
        q = q.where(JournalEntry.incident_type == incident_type)
    if open_only:
        q = q.where(JournalEntry.resolved_on.is_(None))
    q = q.order_by(JournalEntry.entry_on.desc(), JournalEntry.id.desc())
    return [row(session, e) for e in session.scalars(q)]


def _parent_on(session: Session, component_id: int, day: str) -> int | None:
    from bikelog.models import Installation
    for i in session.scalars(select(Installation).where(Installation.component_id == component_id,
                                                        Installation.voided_at.is_(None))):
        if i.installed_at[:10] <= day and (i.removed_at is None or i.removed_at[:10] > day):
            return i.parent_component_id
    return None


def _entries_below(session: Session, component_id: int, include_voided: bool) -> list[JournalEntry]:
    """Journal entries on parts that, on the entry's date, were mounted on this part (directly or deeper)."""
    from bikelog.models import Installation
    below: set[int] = set()
    frontier = {component_id}
    while frontier:   # every part ever mounted below (any time); the date check follows
        kids = set(session.scalars(select(Installation.component_id).where(
            Installation.parent_component_id.in_(frontier), Installation.voided_at.is_(None))))
        frontier = kids - below - {component_id}
        below |= frontier
    if not below:
        return []
    q = select(JournalEntry).where(JournalEntry.component_id.in_(below))
    if not include_voided:
        q = q.where(JournalEntry.voided_at.is_(None))
    out = []
    for e in session.scalars(q):
        cur, seen = e.component_id, set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = _parent_on(session, cur, e.entry_on)
            if cur == component_id:
                out.append(e)
                break
    return out
