"""Chain rotation on a bike: several chains (Chain A, Chain B ...) take turns. One is on the bike; the others
are stored "waxed, ready" (hot waxed, 0 km since) or "dirty, waiting for wax". The hot-wax rule of the chain
on the bike decides when to swap: to the next ready chain, or, when none is ready, to wax the dirty ones.

Nothing here is stored except which bike's rotation a chain is in (component.rotation_bike_id) and its mark;
states come from the hot-wax and wear events (maintenance.chain_row), the timeline from installations.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.models import Component, Installation
from bikelog.services import maintenance as m
from bikelog.services import inventory as inv
from bikelog.services.errors import DomainError
from bikelog.services.usage import usage_since

READY = "READY_TO_INSTALL"
DIRTY = ("NEEDS_HOT_WAX", "NEW_UNWAXED", "UNKNOWN")
SOON = ("DUE_SOON", "DUE", "OVERDUE")


def _members(session: Session, bike_id: int) -> list[Component]:
    on = [c for c in (session.get(Component, r["component_id"]) for r in inv.bike_setup(session, inv.get_bike(session, bike_id)))
          if c.component_type == "CHAIN"]
    rest = session.scalars(select(Component).where(Component.component_type == "CHAIN",
                                                   Component.rotation_bike_id == bike_id,
                                                   Component.status == "ACTIVE").order_by(Component.label))
    out = {c.id: c for c in on}
    for c in rest:
        out.setdefault(c.id, c)
    return sorted(out.values(), key=lambda c: c.label)


def _last_off(session: Session, comp_id: int) -> str:
    """When the chain last came off a bike ('' = never on): the ready chain that rested longest goes on next."""
    return session.scalar(select(Installation.removed_utc).where(
        Installation.component_id == comp_id, Installation.voided_at.is_(None),
        Installation.removed_utc.is_not(None)).order_by(Installation.removed_utc.desc())) or ""


def rotation(session: Session, bike_id: int) -> dict:
    bike = inv.get_bike(session, bike_id)
    comps = _members(session, bike_id)
    rows = [m.chain_row(session, c) for c in comps]
    on = next((r for r in rows if r["state"] == "INSTALLED" and r["location"].get("bike_id") == bike.id), None)
    ready = sorted((r for r in rows if r["state"] == READY), key=lambda r: _last_off(session, r["component_id"]))
    dirty = [r for r in rows if r["state"] in DIRTY]
    wax = None
    if on:
        comp = session.get(Component, on["component_id"])
        rule = next((r for r in m.effective_rules(session, comp) if r.action_code == "WAX_HOT"), None)
        wax = m.rule_status(session, comp, rule) if rule else None
        on["wax_status"] = wax
    prompt = None
    if on and wax and wax["status"] in SOON:
        used = on["km_since_hot_wax"]
        km = f"{used:,.0f} km since hot wax" if used is not None else "no hot wax recorded"
        if ready:
            prompt = {"kind": "SWAP", "to": ready[0]["component_id"], "to_label": ready[0]["label"],
                      "text": f"{on['label']} has {km}. Swap to {ready[0]['label']} (waxed, ready)."}
        else:
            names = [r["label"] for r in dirty] + [on["label"]]
            prompt = {"kind": "WAX", "text": f"{on['label']} has {km} and no waxed chain is ready. "
                                             f"Wax {', '.join(names)}, then put one on."}
    elif not on and ready:
        prompt = {"kind": "INSTALL", "to": ready[0]["component_id"], "to_label": ready[0]["label"],
                  "text": f"No chain on {bike.name}. Put {ready[0]['label']} on (waxed, ready)."}
    return {"bike_id": bike.id, "bike": bike.name, "chains": rows, "on": on["component_id"] if on else None,
            "next_ready": ready[0]["component_id"] if ready else None,
            # the chain on the bike counts as dirty once ridden since its last hot wax (or never hot waxed)
            "dirty": [r["component_id"] for r in dirty] + ([on["component_id"]] if on and on["km_since_hot_wax"] != 0 else []),
            "prompt": prompt, "timeline": timeline(session, bike.id, [c.id for c in comps]),
            "candidates": candidates(session, bike.id)}


def candidates(session: Session, bike_id: int) -> list[dict]:
    """Chains that could join this bike's rotation: active, in no rotation and not on another bike."""
    out = []
    for c in session.scalars(select(Component).where(Component.component_type == "CHAIN", Component.status == "ACTIVE",
                                                     Component.rotation_bike_id.is_(None)).order_by(Component.label)):
        if inv.open_installation(session, c.id) is None:
            out.append({"component_id": c.id, "label": c.label, "mark": c.mark})
    return out


def timeline(session: Session, bike_id: int, chain_ids: list[int]) -> list[dict]:
    """Newest first: each stint of a chain on this bike (with its km) and each hot wax of a rotation chain."""
    rows = []
    for i in session.scalars(select(Installation).join(Component, Component.id == Installation.component_id).where(
            Installation.bike_id == bike_id, Installation.voided_at.is_(None), Component.component_type == "CHAIN")):
        c = session.get(Component, i.component_id)
        km = usage_since(session, c.id, i.installed_utc) - (usage_since(session, c.id, i.removed_utc) if i.removed_utc else 0)
        rows.append({"kind": "ON", "date": i.installed_at[:10], "until": i.removed_at[:10] if i.removed_at else None,
                     "sort": i.installed_utc, "component_id": c.id, "label": c.label, "km": round(km, 1)})
    for cid in chain_ids:
        c = session.get(Component, cid)
        for e in m.events_for(session, component_id=cid):
            if e["action_code"] == "WAX_HOT" and not e["voided"]:
                rows.append({"kind": "WAX", "date": e["performed_on"], "until": None, "sort": e["performed_at"],
                             "component_id": cid, "label": c.label, "km": None})
    rows.sort(key=lambda r: (r["date"], r["kind"] == "ON", r["sort"]), reverse=True)
    for r in rows:
        r.pop("sort")
    return rows


def chain_history(session: Session, comp: Component) -> list[dict]:
    """One chain's wax cycles, oldest first: each hot wax and the km ridden until the next one."""
    waxes = sorted((e for e in m.events_for(session, component_id=comp.id)
                    if e["action_code"] == "WAX_HOT" and not e["voided"]), key=lambda e: e["performed_at"])
    from bikelog.models import MaintenanceEvent
    out = []
    for n, e in enumerate(waxes):
        start = session.get(MaintenanceEvent, e["id"]).sort_utc
        end = session.get(MaintenanceEvent, waxes[n + 1]["id"]).sort_utc if n + 1 < len(waxes) else None
        km = usage_since(session, comp.id, start) - (usage_since(session, comp.id, end) if end else 0)
        out.append({"cycle": n + 1, "waxed_on": e["performed_on"], "km": round(km, 1), "current": end is None})
    return out


def swap(session: Session, bike_id: int, *, to_component_id: int, at: str, work_session_id: int | None = None) -> dict:
    """One click: the chain on the bike comes off (stored, keeps its km) and the chosen one goes on."""
    rot = rotation(session, bike_id)
    new = inv.get_component(session, to_component_id)
    if new.component_type != "CHAIN":
        raise DomainError(f"{new.label} is not a chain")
    if rot["on"] == new.id:
        raise DomainError(f"{new.label} is already on the bike")
    if rot["on"] is None:
        inv.install(session, new.id, at=at, bike_id=bike_id, slot="CHAIN", work_session_id=work_session_id)
        old = None
    else:
        old = inv.get_component(session, rot["on"])
        inv.replace(session, old.id, at=at, new_component_id=new.id, reason="Chain rotation",
                    old_outcome="STORED", work_session_id=work_session_id)
    if new.rotation_bike_id is None:
        new.rotation_bike_id = bike_id
    session.flush()
    return {"off": old.label if old else None, "on": new.label,
            "text": f"{old.label} off, {new.label} on." if old else f"{new.label} on."}


def wax(session: Session, bike_id: int, *, component_ids: list[int], at: str, consumable_id: int | None = None,
        consumable_qty: float | None = None, then_install: int | None = None,
        work_session_id: int | None = None) -> dict:
    """Hot wax several chains at once (they become "waxed, ready"); optionally swap one onto the bike first,
    so the chain coming off is waxed too."""
    if not component_ids:
        raise DomainError("Tick the chains you waxed")
    for cid in component_ids:
        if inv.get_component(session, cid).component_type != "CHAIN":
            raise DomainError("Only chains are hot waxed here")
    swapped = None
    if then_install is not None:
        swapped = swap(session, bike_id, to_component_id=then_install, at=at, work_session_id=work_session_id)
    m.log_batch(session, action_code="WAX_HOT", at=at, component_ids=component_ids, consumable_id=consumable_id,
                consumable_qty=consumable_qty, work_session_id=work_session_id)
    names = [inv.get_component(session, c).label for c in component_ids]
    text = f"Hot waxed {', '.join(names)}."
    if swapped:
        text += f" {swapped['text']}"
    return {"text": text, "swap": swapped}
