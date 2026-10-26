"""Ride incidents: what happened on a ride (flat, shifting, empty battery, numb hands ...) and what it affected.

One incident can affect several things (two flats, both derailleurs). It is stored as one journal issue per
affected thing, sharing an ``incident_group``, so each affected part shows it in its own journal. What can be
picked depends on the incident type (catalog.INCIDENT_OPTIONS) and on the parts that were on the bike on the
ride's date. Incidents are never deleted: removing one voids its entries, and it can be restored.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, INCIDENT_OPTIONS, INCIDENT_TYPES, WHOLE_BIKE, IncidentOption
from bikelog.models import Bike, Component, Installation, JournalEntry, Ride, UsageContribution, new_uuid
from bikelog.services import journal
from bikelog.services.errors import DomainError, NotFound

REMOVED = "incident removed"            # void reason of a removed incident (Restore brings these back)
CHANGED = "taken out of the incident"   # void reason of an affected part unticked while editing


def _ride(session: Session, ride_id: int) -> Ride:
    ride = session.get(Ride, ride_id)
    if ride is None:
        raise NotFound("Ride not found")
    return ride


def parts_on_ride(session: Session, ride: Ride) -> list[dict]:
    """Parts on the ride's bike that day (also those mounted on parts, e.g. tires on a wheel), with the slots
    they sit in from the bike down, plus any other part the ride counted on (e.g. a wheel picked for it)."""
    day = ride.ride_date
    out: dict[int, dict] = {}

    def on_day(i: Installation) -> bool:
        return i.installed_at[:10] <= day and (i.removed_at is None or i.removed_at[:10] > day)

    if ride.bike_id is not None:
        frontier = [(i, (i.slot,)) for i in session.scalars(select(Installation).where(
            Installation.bike_id == ride.bike_id, Installation.voided_at.is_(None))) if on_day(i)]
        while frontier:
            nxt = []
            for inst, path in frontier:
                if inst.component_id in out:
                    continue
                out[inst.component_id] = {"component_id": inst.component_id, "slots": path}
                for k in session.scalars(select(Installation).where(
                        Installation.parent_component_id == inst.component_id, Installation.voided_at.is_(None))):
                    if on_day(k):
                        nxt.append((k, path + (k.slot,)))
            frontier = nxt
    for cid, slot in session.execute(select(UsageContribution.component_id, UsageContribution.slot).where(
            UsageContribution.ride_id == ride.id)):
        out.setdefault(cid, {"component_id": cid, "slots": (slot,)})
    comps = {c.id: c for c in session.scalars(select(Component).where(Component.id.in_(out)))}
    rows = []
    for cid, r in out.items():
        c = comps[cid]
        rows.append({**r, "label": c.label, "component_type": c.component_type})
    rows.sort(key=lambda r: (COMPONENT_TYPES[r["component_type"]].category if r["component_type"] in COMPONENT_TYPES
                             else "", r["label"]))
    return rows


def _matches(opt: IncidentOption, part: dict) -> bool:
    return part["component_type"] in opt.types and (not opt.within or any(s in opt.within for s in part["slots"]))


def choices(session: Session, ride: Ride, incident_type: str) -> list[dict]:
    """What this incident type can affect on this ride: key, label, component_id (None = not a part)."""
    if incident_type not in INCIDENT_TYPES:
        raise DomainError(f"incident_type must be one of {', '.join(INCIDENT_TYPES)}")
    parts = parts_on_ride(session, ride)
    bike = {"key": WHOLE_BIKE, "label": "Whole bike", "component_id": None, "affected": None, "recorded": True}
    opts = INCIDENT_OPTIONS.get(incident_type)
    if opts is None:     # defect / other: any part that was on the bike
        return [bike] + [{"key": f"c{p['component_id']}", "label": p["label"], "component_id": p["component_id"],
                          "affected": None, "recorded": True} for p in parts]
    out: list[dict] = []
    seen: set[int] = set()
    for opt in opts:
        if opt.key == WHOLE_BIKE:
            out.append({**bike, "label": opt.label})
            continue
        if not opt.types:    # not a part (body area, rider)
            out.append({"key": opt.key, "label": opt.label, "component_id": None, "affected": opt.label,
                        "recorded": True})
            continue
        found = [p for p in parts if _matches(opt, p) and p["component_id"] not in seen]
        for p in found:
            seen.add(p["component_id"])
            out.append({"key": f"c{p['component_id']}", "label": f"{opt.label}: {p['label']}",
                        "component_id": p["component_id"], "affected": None, "recorded": True})
        if not found:        # not recorded in Bike Log: the position itself can still be picked
            out.append({"key": opt.key, "label": opt.label, "component_id": None, "affected": opt.label,
                        "recorded": False})
    return out


def all_choices(session: Session, ride_id: int) -> dict[str, list[dict]]:
    ride = _ride(session, ride_id)
    return {code: choices(session, ride, code) for code in INCIDENT_TYPES}


def _key(e: JournalEntry, opts: list[dict]) -> str:
    if e.component_id is not None:
        return f"c{e.component_id}"
    if e.affected:
        return next((o["key"] for o in opts if o["component_id"] is None and o["affected"] == e.affected),
                    f"x:{e.affected}")
    return WHOLE_BIKE


def _pick(session: Session, ride: Ride, incident_type: str, keys: list[str]) -> list[dict]:
    opts = {o["key"]: o for o in choices(session, ride, incident_type)}
    keys = list(dict.fromkeys(keys or [WHOLE_BIKE]))
    bad = [k for k in keys if k not in opts and not k.startswith("x:")]
    if bad:
        raise DomainError(f"{INCIDENT_TYPES[incident_type]}: this ride cannot have {', '.join(bad)} affected")
    return [opts[k] if k in opts else {"key": k, "component_id": None, "affected": k[2:]} for k in keys]


def _entries(session: Session, group: str, *, voided: bool | None = False) -> list[JournalEntry]:
    q = select(JournalEntry).where(JournalEntry.incident_group == group)
    if voided is False:
        q = q.where(JournalEntry.voided_at.is_(None))
    rows = list(session.scalars(q.order_by(JournalEntry.id)))
    if not rows:
        raise NotFound("Incident not found")
    return rows


def _add(session: Session, ride: Ride, incident_type: str, pick: dict, *, group: str, text: str | None,
         resolved_on: str | None) -> JournalEntry:
    return journal.add(session, text=text, ride_id=ride.id, incident_type=incident_type, incident_group=group,
                       component_id=pick["component_id"], affected=pick["affected"],
                       bike_id=None if pick["component_id"] else ride.bike_id, resolved_on=resolved_on)


def log(session: Session, ride_id: int, *, incident_type: str, affected: list[str] | None = None,
        text: str | None = None, resolved_on: str | None = None) -> str:
    """One incident with everything it affected (choice keys from ``choices``). Returns its group id."""
    ride = _ride(session, ride_id)
    picks = _pick(session, ride, incident_type, affected or [])
    if ride.bike_id is None and any(p["component_id"] is None for p in picks):
        raise DomainError("This ride has no bike; pick the parts that were affected or set the ride's bike first")
    group = new_uuid()
    for p in picks:
        _add(session, ride, incident_type, p, group=group, text=text, resolved_on=resolved_on)
    return group


def update(session: Session, group: str, *, incident_type: str | None = None, affected: list[str] | None = None,
           text: str | None = None, resolved_on: str | None = None, fields: set[str] = frozenset()) -> str:
    """Change an incident: type, details, fixed date and what it affected. Unticked parts are voided (they
    stay in the history), newly ticked ones are added to the same incident."""
    rows = _entries(session, group)
    ride = _ride(session, rows[0].ride_id) if rows[0].ride_id else None
    if ride is None:
        raise DomainError("This incident is not linked to a ride")
    itype = incident_type or rows[0].incident_type
    current = choices(session, ride, itype)
    have = {_key(e, current): e for e in rows}
    if "affected" in fields or itype != rows[0].incident_type:
        picks = _pick(session, ride, itype, affected if "affected" in fields else list(have))
    else:
        picks = [{"key": k} for k in have]
    want = {p["key"] for p in picks}
    if not want:
        raise DomainError("Pick at least one thing that was affected")
    first = rows[0]
    new_text = text if "text" in fields else (None if first.text == INCIDENT_TYPES.get(first.incident_type)
                                              else first.text)
    new_resolved = resolved_on if "resolved_on" in fields else first.resolved_on
    for k, e in have.items():
        if k not in want:
            journal.void(session, e.id, CHANGED)
    for p in picks:
        if p["key"] in have:
            e = have[p["key"]]
            upd: dict = {"incident_type": itype, "resolved_on": new_resolved}
            if "text" in fields or itype != first.incident_type:
                upd["text"] = (new_text or "").strip() or INCIDENT_TYPES[itype]
            journal.update(session, e.id, **upd)
        else:
            _add(session, ride, itype, p, group=group, text=new_text, resolved_on=new_resolved)
    return group


def remove(session: Session, group: str) -> None:
    for e in _entries(session, group):
        journal.void(session, e.id, REMOVED)


def restore(session: Session, group: str) -> None:
    rows = [e for e in _entries(session, group, voided=None) if e.voided_at and e.void_reason == REMOVED]
    if not rows:
        raise DomainError("Nothing to restore: this incident was not removed")
    for e in rows:
        e.voided_at, e.void_reason = None, None
    session.flush()


def _group_row(session: Session, rows: list[JournalEntry], *, removed: bool) -> dict:
    first = rows[0]
    ride = session.get(Ride, first.ride_id) if first.ride_id else None
    opts = choices(session, ride, first.incident_type) if ride is not None else []
    affected = []
    for e in rows:
        comp = session.get(Component, e.component_id) if e.component_id else None
        affected.append({"key": _key(e, opts), "component_id": e.component_id,
                         "label": comp.label if comp else (e.affected or "Whole bike")})
    detail = None if first.text == INCIDENT_TYPES.get(first.incident_type) else first.text
    bike = session.get(Bike, first.bike_id) if first.bike_id else None
    return {"group": first.incident_group, "incident_type": first.incident_type,
            "label": INCIDENT_TYPES.get(first.incident_type, first.incident_type), "on": first.entry_on,
            "text": detail, "resolved_on": first.resolved_on, "open": not first.resolved_on,
            "affected": affected, "removed": removed, "ride_id": first.ride_id,
            "ride_label": journal._ride_label(ride), "ride_conditions": ride.conditions if ride else None,
            "bike_id": first.bike_id, "bike": bike.name if bike else None,
            "edited": any(e.updated_at for e in rows)}


def _grouped(session: Session, q) -> list[dict]:
    groups: dict[str, list[JournalEntry]] = {}
    for e in session.scalars(q.where(JournalEntry.incident_type.is_not(None)).order_by(JournalEntry.id)):
        groups.setdefault(e.incident_group or e.uuid, []).append(e)
    out = []
    for rows in groups.values():
        live = [e for e in rows if not e.voided_at]
        if live:
            out.append(_group_row(session, live, removed=False))
        else:
            gone = [e for e in rows if e.void_reason == REMOVED]
            if gone:
                out.append(_group_row(session, gone, removed=True))
    return out


def ride_incidents(session: Session, ride_id: int) -> list[dict]:
    """The ride's incidents (one row per incident with everything it affected), removed ones last."""
    _ride(session, ride_id)
    out = _grouped(session, select(JournalEntry).where(JournalEntry.ride_id == ride_id))
    return sorted(out, key=lambda r: r["removed"])


def bike_incidents(session: Session, bike_id: int) -> list[dict]:
    """All incidents on a bike, newest first (open ones before solved ones), removed ones last."""
    out = _grouped(session, select(JournalEntry).where(JournalEntry.bike_id == bike_id))
    out.sort(key=lambda r: r["on"], reverse=True)
    return sorted(out, key=lambda r: (r["removed"], not r["open"]))


def all_incidents(session: Session, *, bike_id: int | None = None, component_id: int | None = None,
                  incident_type: str | None = None, open_only: bool = False) -> list[dict]:
    """Every incident (one row per incident, with all it affected), newest first, for Rides → Incidents.
    A filter on a part or bike picks the incidents that touch it; the row still lists everything affected."""
    q = select(JournalEntry.incident_group).where(JournalEntry.incident_type.is_not(None),
                                                  JournalEntry.voided_at.is_(None))
    if bike_id is not None:
        q = q.where(JournalEntry.bike_id == bike_id)
    if component_id is not None:
        q = q.where(JournalEntry.component_id == component_id)
    if incident_type:
        q = q.where(JournalEntry.incident_type == incident_type)
    if open_only:
        q = q.where(JournalEntry.resolved_on.is_(None))
    groups = set(session.scalars(q))
    if not groups:
        return []
    out = [r for r in _grouped(session, select(JournalEntry).where(JournalEntry.incident_group.in_(groups)))
           if not r["removed"]]
    return sorted(out, key=lambda r: r["on"], reverse=True)


def count_for_ride(session: Session, ride_id: int) -> int:
    return len({g for g in session.scalars(select(JournalEntry.incident_group).where(
        JournalEntry.ride_id == ride_id, JournalEntry.incident_type.is_not(None), JournalEntry.voided_at.is_(None)))})
