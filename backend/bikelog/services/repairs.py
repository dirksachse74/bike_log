"""Fixing an incident: what was done about each damaged part.

An incident says what happened (a flat on the rear tube); a repair says what you did about it, per affected
part: REPLACED (a spare, one from stock or a new item goes in; the old part is removed and keeps its km),
REPAIRED (a patched tube, an adjusted derailleur), or nothing yet (the incident stays open). Each fix is
one work session holding the part change, the stock use or the patch event, so undoing the fix undoes them
too. When every affected part is handled the incident is solved on the fix date.

Tubes are usually kept as stock items ("Conti Race 28, 3 at home"): replacing an untracked tube takes one
from stock. Tires (and tubes you track one by one) are individual parts installed on the wheel.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, INCIDENT_OPTIONS, INCIDENT_TYPES, WHEEL_TYPES
from bikelog.models import Component, JournalEntry, MaintenanceEvent, Ride
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import spares as spares_svc
from bikelog.services import stock, worksessions
from bikelog.services.errors import DomainError, NotFound

REPAIRS = {"REPLACED": "replaced", "REPAIRED": "repaired"}
DAMAGE_TYPES = {"TUBE": "INNER_TUBE", "TIRE": "TIRE"}
SLOT_OF = {"TUBE": "TUBE", "TIRE": "TIRE"}
WHEEL_NAMES = {"FRONT_WHEEL": "front", "REAR_WHEEL": "rear"}
# "Front tube", "Rear tire" ... (and the older "Front tire" by name) → wheel and what was damaged
_POSITIONS = {opt.label: (opt.within[0], "TUBE" if "INNER_TUBE" in opt.types else "TIRE")
              for opt in INCIDENT_OPTIONS["FLAT"]}


def _entries(session: Session, group: str) -> list[JournalEntry]:
    rows = list(session.scalars(select(JournalEntry).where(JournalEntry.incident_group == group,
                                                           JournalEntry.voided_at.is_(None))
                                .order_by(JournalEntry.id)))
    if not rows:
        raise NotFound("Incident not found")
    return rows


def wheel_on_bike(session: Session, bike_id: int | None, wheel: str) -> Component | None:
    """The front or rear wheel on the bike now (also inside a wheelset)."""
    if bike_id is None:
        return None
    row = next((r for r in inv.bike_setup(session, inv.get_bike(session, bike_id))
                if r["component_type"] == wheel), None)
    return session.get(Component, row["component_id"]) if row else None


def _part_on_wheel(session: Session, wheel: Component | None, damage: str) -> Component | None:
    if wheel is None:
        return None
    from bikelog.models import Installation
    for i in session.scalars(select(Installation).where(Installation.parent_component_id == wheel.id,
                                                        Installation.removed_utc.is_(None),
                                                        Installation.voided_at.is_(None))):
        c = session.get(Component, i.component_id)
        if c.component_type == DAMAGE_TYPES[damage]:
            return c
    return None


def describe(session: Session, e: JournalEntry) -> dict:
    """What an affected entry is: a recorded part, a tube/tire position without a recorded part, or
    something else (a body area, the whole bike, a part not in Bike Log)."""
    comp = session.get(Component, e.component_id) if e.component_id else None
    out = {"entry_id": e.id, "label": comp.label if comp else (e.affected or "Whole bike"),
           "component_id": e.component_id, "damage": None, "wheel": None, "installed": False,
           "repair": e.repair, "repair_text": e.repair_text, "repaired_on": e.repaired_on}
    if e.incident_type == "SPOKE":       # a broken spoke: repaired on the wheel, counted there
        wheel = comp if comp is not None and comp.component_type in WHEEL_TYPES else None
        if wheel is None and e.affected in ("Front wheel", "Rear wheel"):
            out["wheel"] = "FRONT_WHEEL" if e.affected == "Front wheel" else "REAR_WHEEL"
        else:
            out["wheel"] = wheel.component_type if wheel else None
        out["kind"], out["wheel_id"] = "SPOKE", wheel.id if wheel else None
        return out
    if comp is not None:
        out["damage"] = {"INNER_TUBE": "TUBE", "TIRE": "TIRE"}.get(comp.component_type)
        loc = inv.location(session, comp)
        out["installed"] = loc["state"] == "INSTALLED"
        parent = session.get(Component, loc.get("parent_component_id")) if loc.get("parent_component_id") else None
        if parent is not None and parent.component_type in WHEEL_TYPES:
            out["wheel"] = parent.component_type
        out["kind"] = "PART"
    elif e.affected in _POSITIONS and e.incident_type == "FLAT":
        out["wheel"], out["damage"] = _POSITIONS[e.affected]
        out["kind"] = "POSITION"
    else:
        out["kind"] = "OTHER"
    return out


def _stock_lines(session: Session, ctype: str) -> list[dict]:
    return [{"id": line["id"], "name": line["name"], "unit": line["unit"], "qty": (line["stock"] or {}).get("qty", 0)}
            for line in stock.consumable_stock(session)
            if line["component_type"] == ctype and line["tracking_mode"] == "COUNTED"
            and (line["stock"] or {}).get("qty", 0) >= 1]


def position_options(session: Session, bike_id: int | None, wheel: str, damage: str) -> dict:
    """Sources for a tube or tire at a wheel position without a recorded part: stock, stored spares (when
    the wheel is recorded, they get installed on it) or a new one."""
    ctype = DAMAGE_TYPES[damage]
    w = wheel_on_bike(session, bike_id, wheel)
    spares = [{"id": c.id, "label": c.label} for c in stock.individual_spares(session, ctype, None)] if w else []
    return {"wheel_label": w.label if w else None, "stock": _stock_lines(session, ctype), "spares": spares,
            "installed_component_id": (p.id if (p := _part_on_wheel(session, w, damage)) else None),
            "tracks_new": w is not None and damage == "TIRE"}


def fix_options(session: Session, group: str) -> dict:
    rows = _entries(session, group)
    first = rows[0]
    ride = session.get(Ride, first.ride_id) if first.ride_id else None
    bike_id = ride.bike_id if ride else first.bike_id
    parts = []
    for e in rows:
        d = describe(session, e)
        if d["repair"]:
            parts.append({**d, "options": None})
            continue
        if d["kind"] == "SPOKE":
            if d["wheel_id"] is None and d["wheel"]:
                w = wheel_on_bike(session, bike_id, d["wheel"])
                d["wheel_id"] = w.id if w else None
            d["options"] = {"replace": True, "spoke": True, "stock": _stock_lines(session, "SPOKES"), "spares": []}
            d["repair_label"] = "Trued / re-tensioned"
            parts.append(d)
            continue
        if d["kind"] == "PART" and d["installed"]:
            o = spares_svc.replace_options(session, e.component_id)
            d["options"] = {"replace": True, "spares": [{"id": s["id"], "label": s["label"]} for s in o["spares"]],
                            "stock": [{"id": s["id"], "name": s["name"], "unit": s["unit"],
                                       "qty": (s["stock"] or {}).get("qty", 0)} for s in o["stock"]],
                            "suggested_outcome": o["suggested_outcome"], "outcomes": o["outcomes"]}
        elif d["kind"] == "POSITION":
            d["options"] = {"replace": True, **position_options(session, bike_id, d["wheel"], d["damage"])}
        else:
            d["options"] = {"replace": d["kind"] == "OTHER", "spares": [], "stock": []}
        d["repair_label"] = "Patched" if d["damage"] == "TUBE" else "Repaired or adjusted"
        parts.append(d)
    return {"group": group, "label": INCIDENT_TYPES.get(first.incident_type, first.incident_type),
            "ride_date": ride.ride_date if ride else first.entry_on, "bike_id": bike_id, "parts": parts}


def _patches(session: Session, component_id: int) -> int:
    return session.scalar(select(func.count(MaintenanceEvent.id)).where(
        MaintenanceEvent.component_id == component_id, MaintenanceEvent.action_code == "TUBE_PATCH",
        MaintenanceEvent.voided_at.is_(None))) or 0


def replace_at_position(session: Session, *, bike_id: int | None, wheel: str, damage: str, at: str,
                        source: dict, work_session_id: int, reason: str) -> str:
    """Put a tube or tire in at a wheel position that has no recorded part of that kind. Returns the text."""
    ctype = DAMAGE_TYPES[damage]
    what = COMPONENT_TYPES[ctype].name.lower()
    w = wheel_on_bike(session, bike_id, wheel)
    kind = source.get("kind")
    if kind == "stock":
        line = stock.get(session, int(source["id"]))
        if line.component_type != ctype:
            raise DomainError(f"{line.name} is not stock of {what}s")
        if damage == "TIRE" and w is not None:
            comp = stock.draw_component(session, line.id, on=at, work_session_id=work_session_id)
            inv.install(session, comp.id, at=at, parent_component_id=w.id, slot=SLOT_OF[damage],
                        work_session_id=work_session_id)
            return f"replaced with {comp.label} from stock"
        stock.use(session, line.id, qty=1, on=at, note=f"{reason}: {WHEEL_NAMES[wheel]} {what}",
                  work_session_id=work_session_id)
        left = stock.level(session, line)["qty"]
        return f"replaced with one from stock ({line.name}, {left:g} left)"
    if kind == "spare":
        if w is None:
            raise DomainError(f"No {WHEEL_NAMES[wheel]} wheel recorded on this bike to put {what} on. "
                              "Take one from stock, or install the wheel first.")
        comp = inv.get_component(session, int(source["id"]))
        if comp.component_type != ctype:
            raise DomainError(f"{comp.label} is not a {what}")
        inv.install(session, comp.id, at=at, parent_component_id=w.id, slot=SLOT_OF[damage],
                    work_session_id=work_session_id)
        return f"replaced with {comp.label}"
    if kind == "new" and damage == "TIRE" and w is not None:
        comp = inv.create_component(session, component_type=ctype,
                                    label=(source.get("label") or "").strip() or f"Tire {WHEEL_NAMES[wheel]} (new)",
                                    prior_usage="NEW", purchase_date=at[:10], work_session_id=work_session_id)
        inv.install(session, comp.id, at=at, parent_component_id=w.id, slot=SLOT_OF[damage],
                    work_session_id=work_session_id)
        return f"replaced with {comp.label}"
    if kind in ("new", "untracked"):
        return f"replaced with a new {what} (not tracked)"
    raise DomainError("Pick where the new part came from: stock, a spare or a new one")


def _replace_part(session: Session, comp: Component, *, at: str, source: dict, outcome: str | None,
                  work_session_id: int, reason: str) -> str:
    kind = source.get("kind")
    kw: dict = {"at": at, "reason": reason, "old_outcome": outcome, "work_session_id": work_session_id}
    if kind == "spare":
        kw["new_component_id"] = int(source["id"])
    elif kind == "stock":
        kw["from_stock_id"] = int(source["id"])
    elif kind == "same":
        kw["same_product"] = True
    elif kind in ("new", "untracked"):
        kw["new"] = {"label": (source.get("label") or "").strip() or None}
    else:
        raise DomainError("Pick where the new part came from: a spare, stock or a new one")
    children = [c["component_id"] for c in spares_svc.replace_options(session, comp.id)["children"] if c["carry_over"]]
    res = inv.replace(session, comp.id, carry_over=children, **kw)
    return f"replaced with {res['new_label']}"


def _fix_spoke(session: Session, d: dict, bike_id: int | None, p: dict, *, at: str, note: str | None,
               ws_id: int) -> str:
    """A broken spoke: replaced (counts towards re-lacing; one spoke from stock when picked) or the wheel
    trued / re-tensioned. Logged on the wheel; without a recorded wheel only the text is kept."""
    wheel = session.get(Component, d["wheel_id"]) if d.get("wheel_id") else \
        (wheel_on_bike(session, bike_id, d["wheel"]) if d.get("wheel") else None)
    if p["action"] == "REPAIRED":
        if wheel is not None:
            m.log_event(session, action_code="WHEEL_TRUE", at=at, component_id=wheel.id, notes=note,
                        work_session_id=ws_id)
        return "wheel trued / re-tensioned"
    source = p.get("source") or {}
    line_id = int(source["id"]) if source.get("kind") == "stock" else None
    if line_id is not None and stock.get(session, line_id).component_type != "SPOKES":
        raise DomainError("Pick spare spokes from stock, or a spoke not from stock")
    if wheel is None:
        if line_id is not None:
            stock.use(session, line_id, qty=1, on=at, note="broken spoke", work_session_id=ws_id)
        return "spoke replaced (wheel not recorded, not counted)"
    m.log_event(session, action_code="SPOKE_REPLACE", at=at, component_id=wheel.id, notes=note,
                consumable_id=line_id, consumable_qty=1 if line_id else None, work_session_id=ws_id)
    info = m.spoke_info(session, wheel)
    text = f"spoke replaced ({info['broken']} of {info['relace_after']} before a re-lace)"
    if line_id is not None:
        text += f", one from stock ({stock.level(session, stock.get(session, line_id))['qty']:g} left)"
    return text


def fix(session: Session, group: str, *, at: str, parts: list[dict], note: str | None = None) -> dict:
    """Record what was done about each affected part (``parts``: entry_id, action REPLACED / REPAIRED /
    NONE, source for a replacement, old_outcome). Solves the incident when every part is handled."""
    rows = {e.id: e for e in _entries(session, group)}
    first = next(iter(rows.values()))
    ride = session.get(Ride, first.ride_id) if first.ride_id else None
    bike_id = ride.bike_id if ride else first.bike_id
    if ride is not None and at[:10] < ride.ride_date:
        raise DomainError("The fix cannot be before the ride")
    todo = [p for p in parts if p.get("action") in REPAIRS]
    bad = [p for p in parts if p.get("action") not in (*REPAIRS, "NONE", None)]
    if bad:
        raise DomainError("For each part say: replaced, repaired (patched), or nothing yet")
    if not todo:
        raise DomainError("Say what you did for at least one part (or leave the incident open)")
    label = INCIDENT_TYPES.get(first.incident_type, first.incident_type)
    ws = worksessions.begin(session, at=at, bike_id=bike_id, title=f"Fix: {label}", notes=note)
    texts = []
    for p in todo:
        e = rows.get(int(p["entry_id"]))
        if e is None:
            raise DomainError("That part is not in this incident")
        if e.repair:
            raise DomainError(f"{describe(session, e)['label']} is already {REPAIRS[e.repair]}; undo that fix first")
        d = describe(session, e)
        comp = session.get(Component, e.component_id) if e.component_id else None
        if d["kind"] == "SPOKE":
            text = _fix_spoke(session, d, bike_id, p, at=at, note=note, ws_id=ws.id)
        elif p["action"] == "REPAIRED":
            if comp is not None and comp.component_type == "INNER_TUBE":
                m.log_event(session, action_code="TUBE_PATCH", at=at, component_id=comp.id, notes=note,
                            work_session_id=ws.id)
                n = _patches(session, comp.id)
                text = f"patched (patch {n} on this tube)"
            else:
                text = "patched" if d["damage"] == "TUBE" else "repaired or adjusted"
        else:
            source = p.get("source") or {}
            if comp is not None:
                if not d["installed"]:
                    raise DomainError(f"{comp.label} is not installed any more; it was changed already")
                text = _replace_part(session, comp, at=at, source=source, outcome=p.get("old_outcome"),
                                     work_session_id=ws.id, reason=label.lower())
            elif d["kind"] == "POSITION":
                text = replace_at_position(session, bike_id=bike_id, wheel=d["wheel"], damage=d["damage"], at=at,
                                           source=source, work_session_id=ws.id, reason=label.lower())
            else:
                text = "replaced (not tracked)"
        e.repair, e.repair_text, e.repaired_on, e.repair_session_id = p["action"], text, at[:10], ws.id
        texts.append(f"{d['label']}: {text}")
    live = list(rows.values())
    solved = all(e.repair for e in live)
    if solved:
        for e in live:
            e.resolved_on = max(x.repaired_on for x in live)
    session.flush()
    return {"solved": solved, "work_session_id": ws.id, "texts": texts}


def undo_fix(session: Session, group: str) -> dict:
    """Undo the fixes of an incident: their work sessions are undone (parts, stock and patch events come
    back) and the incident is open again."""
    sessions = {e.repair_session_id for e in _entries(session, group) if e.repair_session_id}
    if not sessions:
        raise DomainError("Nothing to undo: no fix recorded for this incident")
    for ws_id in sorted(sessions, reverse=True):
        ws = worksessions.get(session, ws_id)
        if not ws.undone_at:
            worksessions.undo(session, ws_id, "fix undone")
    return {"undone": len(sessions)}


def clear_for_session(session: Session, ws_id: int) -> None:
    """Called when a work session is undone: its fixes are taken back and their incidents reopen."""
    groups = set()
    for e in session.scalars(select(JournalEntry).where(JournalEntry.repair_session_id == ws_id)):
        e.repair = e.repair_text = e.repaired_on = e.repair_session_id = None
        groups.add(e.incident_group)
    for g in groups:
        for e in session.scalars(select(JournalEntry).where(JournalEntry.incident_group == g)):
            e.resolved_on = None
    session.flush()
