"""Journal: dated free-text notes on a bike or a part, such as an issue noticed on a ride.

One place for notes: the journal of a part also shows the notes written on its maintenance entries
(symptom, work done, notes), and a bike's journal shows the entries of the parts that were on it.
Maintenance rows are shown read-only; they are edited where they were logged.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS
from bikelog.models import Component, JournalEntry, MaintenanceEvent
from bikelog.services import settings
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import get_bike, get_component, location
from bikelog.timeutil import parse_when, utc_now

KINDS = {"NOTE": "Note", "ISSUE": "Issue"}


def _date(session: Session, value: str) -> str:
    return parse_when(value, settings.tz(session)).local_date


def add(session: Session, *, text: str, on: str, bike_id: int | None = None, component_id: int | None = None,
        kind: str = "NOTE", resolved_on: str | None = None) -> JournalEntry:
    text = (text or "").strip()
    if not text:
        raise DomainError("Write something in the note")
    if kind not in KINDS:
        raise DomainError(f"kind must be one of {', '.join(KINDS)}")
    if component_id is not None:
        comp = get_component(session, component_id)
        if bike_id is None:
            bike_id = location(session, comp).get("bike_id")
    elif bike_id is not None:
        get_bike(session, bike_id)
    else:
        raise DomainError("A journal entry belongs to a bike or a part")
    e = JournalEntry(bike_id=bike_id, component_id=component_id, entry_on=_date(session, on), kind=kind, text=text,
                     resolved_on=_date(session, resolved_on) if resolved_on and kind == "ISSUE" else None)
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


def row(session: Session, e: JournalEntry) -> dict:
    comp = session.get(Component, e.component_id) if e.component_id else None
    return {"id": e.id, "source": "JOURNAL", "on": e.entry_on, "kind": e.kind, "text": e.text,
            "resolved_on": e.resolved_on, "open_issue": e.kind == "ISSUE" and not e.resolved_on,
            "bike_id": e.bike_id, "component_id": e.component_id, "component_label": comp.label if comp else None,
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
            "resolved_on": None, "open_issue": False, "bike_id": ev.bike_id, "component_id": ev.component_id,
            "component_label": comp.label if comp else None, "edited": False, "voided": False}


def entries(session: Session, *, bike_id: int | None = None, component_id: int | None = None,
            include_voided: bool = False, include_maintenance: bool = True) -> list[dict]:
    if (bike_id is None) == (component_id is None):
        raise DomainError("Show the journal of one bike or one part")
    target = (JournalEntry.bike_id == bike_id) if bike_id is not None else (JournalEntry.component_id == component_id)
    q = select(JournalEntry).where(target)
    if not include_voided:
        q = q.where(JournalEntry.voided_at.is_(None))
    rows = [row(session, e) for e in session.scalars(q)]
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
