"""Assemblies: parts made of parts, for drilling down.

* A part's tree: what is mounted on it now (wheelset → front / rear wheel → hub → bearings, tire, spokes ...),
  each with its km and how many reminders need attention.
* A bike's groupset: not a stored record but the parts in the groupset positions of the bike now
  (drivetrain, shifting, brakes and the Di2 / AXS battery). A new chain belongs to it as soon as it is
  installed; a part taken off leaves it. Its page combines their km, maintenance, journal and incidents.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES
from bikelog.models import Component, Installation, PurchaseBundle
from bikelog.services import incidents as incidents_svc
from bikelog.services import journal
from bikelog.services import maintenance as m
from bikelog.services.inventory import bike_setup, get_bike, location, open_installation
from bikelog.services.usage import bike_hours_since, bike_km_since, component_usage

GROUPSET_CATEGORIES = ("Drivetrain", "Brakes", "Controls")
NEEDS_ACTION = ("OVERDUE", "DUE", "DUE_SOON", "ATTENTION")


def in_groupset(component_type: str | None) -> bool:
    """Same grouping as "Installed now" on the bike page: the Di2 / AXS battery belongs to the shifting."""
    t = COMPONENT_TYPES.get(component_type or "")
    return component_type == "BATTERY" or (t is not None and t.category in GROUPSET_CATEGORIES)


def _node(session: Session, comp: Component, inst: Installation, depth: int) -> dict:
    due = [r for r in m.component_status(session, comp) if r["status"] in NEEDS_ACTION]
    return {"component_id": comp.id, "label": comp.label, "component_type": comp.component_type,
            "type_name": COMPONENT_TYPES[comp.component_type].name, "slot": inst.slot, "since": inst.installed_at,
            "usage": component_usage(session, comp), "due": len(due), "depth": depth,
            "children": tree(session, comp, depth + 1)}


def tree(session: Session, comp: Component, depth: int = 0) -> list[dict]:
    """The parts mounted on this part now, each with the parts mounted on it."""
    rows = session.scalars(select(Installation).where(Installation.parent_component_id == comp.id,
                                                      Installation.removed_utc.is_(None),
                                                      Installation.voided_at.is_(None))
                           .order_by(Installation.slot))
    return [_node(session, session.get(Component, i.component_id), i, depth) for i in rows]


def _flatten(nodes: list[dict]) -> list[dict]:
    out = []
    for n in nodes:
        out.append(n)
        out += _flatten(n["children"])
    return out


def groupset_bike(session: Session, comp: Component) -> int | None:
    """The bike whose groupset this part belongs to now, for a link to the groupset page."""
    if not in_groupset(comp.component_type):
        return None
    bike_id = location(session, comp).get("bike_id")
    if bike_id is None:
        return None
    bike = get_bike(session, bike_id)
    _, nodes = _members(session, bike)
    return bike.id if comp.id in {n["component_id"] for n in _flatten(nodes)} else None


def _members(session: Session, bike) -> tuple[list[dict], list[dict]]:
    """Top: groupset parts mounted on the bike, plus groupset parts mounted on a part outside the groupset
    (cassette and rotors on the wheels), each with what is mounted on it. The cassette and rotors stay listed
    under their wheel on the bike page too; they move with the wheels."""
    setup = bike_setup(session, bike)
    types = {r["component_id"]: r["component_type"] for r in setup}
    top = [r for r in setup if in_groupset(r["component_type"])
           and (r["depth"] == 0 or not in_groupset(types.get(r["parent_component_id"])))]
    nodes = []
    for r in top:
        n = _node(session, session.get(Component, r["component_id"]), open_installation(session, r["component_id"]), 0)
        if r["depth"]:
            n["on"] = next((x["label"] for x in setup if x["component_id"] == r["parent_component_id"]), None)
        nodes.append(n)
    return top, nodes


def _name(session: Session, comps: list[Component]) -> str:
    """The bundle the parts were bought in (a groupset import), else the most common maker."""
    bundle_ids = {c.bundle_id for c in comps if c.bundle_id}
    if bundle_ids:
        for b in session.scalars(select(PurchaseBundle).where(PurchaseBundle.id.in_(bundle_ids),
                                                              PurchaseBundle.voided_at.is_(None))
                                 .order_by(PurchaseBundle.id)):
            return b.name
    makers = Counter(c.product.maker for c in comps if c.product and c.product.maker)
    return f"{makers.most_common(1)[0][0]} groupset" if makers else "Groupset"


def groupset_summary(session: Session, bike) -> dict | None:
    """One line for "Installed now": name, how many parts, how many need attention."""
    top, nodes = _members(session, bike)
    if not nodes:
        return None
    members = _flatten(nodes)
    return {"name": _name(session, [session.get(Component, n["component_id"]) for n in members]),
            "parts": len(members), "due": sum(n["due"] for n in members),
            "top": [n["label"] for n in nodes], "since": min(r["since"] for r in top)}


def groupset(session: Session, bike_id: int) -> dict:
    """The groupset page: combined km, service tasks, maintenance log, journal and incidents of its parts."""
    bike = get_bike(session, bike_id)
    top, nodes = _members(session, bike)
    members = _flatten(nodes)
    ids = [n["component_id"] for n in members]
    comps = [session.get(Component, i) for i in ids]
    # km and hours on this bike since the first groupset part still on it was installed
    first = min((open_installation(session, r["component_id"]).installed_utc for r in top), default=None)
    hours, untimed = bike_hours_since(session, bike.id, first) if first else (0.0, 0)
    events = sorted((e for i in ids for e in m.events_for(session, component_id=i)),
                    key=lambda e: (e["performed_at"], e["id"]), reverse=True)
    seen_notes, notes = set(), []
    for i in ids:
        for e in journal.entries(session, component_id=i, include_maintenance=False):
            if not e.get("incident_type") and e["id"] not in seen_notes:
                seen_notes.add(e["id"])
                notes.append(e)
    notes.sort(key=lambda e: (e["on"], e["id"]), reverse=True)
    seen, incidents = set(), []
    for i in ids:
        for row in incidents_svc.all_incidents(session, component_id=i):
            if row["group"] not in seen:
                seen.add(row["group"])
                incidents.append(row)
    incidents.sort(key=lambda r: r["on"], reverse=True)
    tasks = [r for r in m.queue(session, bike_id=bike.id, include_ok=True) if r["component_id"] in set(ids)]
    return {"bike_id": bike.id, "bike": bike.name, "name": _name(session, comps) if comps else None,
            "since": min((r["since"] for r in top), default=None),
            "stats": {"km": bike_km_since(session, bike.id, first) if first else 0.0, "hours": hours,
                      "rides_without_time": untimed, "parts": len(members),
                      "due": sum(n["due"] for n in members)},
            "parts": nodes, "events": events, "journal": notes, "incidents": incidents, "tasks": tasks}
