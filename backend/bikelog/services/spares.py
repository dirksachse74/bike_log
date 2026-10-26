"""Read models for the Inventory screen and the Replace dialog.

Condition (new / used), readiness (ready, needs hot wax, awaiting repair, worn) and storage
location are kept apart: a stored chain can be a used spare that still needs waxing.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, DISPOSITIONS, ON_BIKE_TOO, OUT_OF_USE
from bikelog.models import Bike, Component, ComponentDisposition, Installation, ProductCompatibility
from bikelog.services import maintenance as m
from bikelog.services import stock
from bikelog.services import worksessions
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import get_component, location, open_installation
from bikelog.services.usage import component_usage


def compatibility(session: Session, product_id: int | None) -> list[dict]:
    if not product_id:
        return []
    bikes = dict(session.execute(select(Bike.id, Bike.name)).all())
    return [{"bike_id": c.bike_id, "bike": bikes.get(c.bike_id), "verified": c.verified, "note": c.note}
            for c in session.scalars(select(ProductCompatibility).where(ProductCompatibility.product_id == product_id)
                                     .order_by(ProductCompatibility.verified.desc()))]


def set_compatibility(session: Session, product_id: int, bike_id: int, verified: bool, note: str | None) -> dict:
    row = session.scalar(select(ProductCompatibility).where(ProductCompatibility.product_id == product_id,
                                                            ProductCompatibility.bike_id == bike_id))
    if row is None:
        row = ProductCompatibility(product_id=product_id, bike_id=bike_id)
        session.add(row)
    row.verified, row.note = verified, note
    session.flush()
    return {"product_id": product_id, "bike_id": bike_id, "verified": verified}


def _ever_used(session: Session, comp: Component, usage: dict) -> bool:
    if comp.prior_usage != "NEW" or usage["total_km"] > 0:
        return True
    return bool(session.scalar(select(Installation.id).where(Installation.component_id == comp.id,
                                                             Installation.voided_at.is_(None)).limit(1)))


def item_row(session: Session, comp: Component, chains: dict[int, dict] | None = None) -> dict:
    loc = location(session, comp)
    usage = component_usage(session, comp)
    used = _ever_used(session, comp, usage)
    if comp.status == "RETIRED":
        state = comp.disposition if comp.disposition in OUT_OF_USE else "RETIRED"
    elif loc["state"] in ("INSTALLED", "IN_USE"):
        state = "INSTALLED"        # shoes in use are listed with the parts in use
    elif comp.disposition == "AWAITING_SERVICE":
        state = "AWAITING_SERVICE"
    else:
        state = "USED_SPARE" if used else "NEW_SPARE"
    readiness, readiness_text = None, None
    if state in ("NEW_SPARE", "USED_SPARE"):
        readiness, readiness_text = "READY", "Ready to install"
        ch = (chains or {}).get(comp.id)
        if ch and ch["state"] in ("NEEDS_HOT_WAX", "NEW_UNWAXED", "UNKNOWN"):
            readiness, readiness_text = "NEEDS_PREPARATION", ch["text"]
        elif ch and ch["state"] == "WORN":
            readiness, readiness_text = "WORN", ch["text"]
    elif state == "AWAITING_SERVICE":
        readiness, readiness_text = "NEEDS_REPAIR", "Awaiting preparation or repair"
    t = COMPONENT_TYPES[comp.component_type]
    product = f"{comp.product.maker or ''} {comp.product.model}".strip() if comp.product else None
    state_text = {"NEW_SPARE": "New spare", "USED_SPARE": "Used spare",
                  "INSTALLED": "In use (worn)" if loc["state"] == "IN_USE" else "Installed",
                  "AWAITING_SERVICE": "Awaiting preparation or repair"}.get(state, DISPOSITIONS.get(state, state))
    return {"id": comp.id, "label": comp.label, "component_type": comp.component_type, "type_name": t.name,
            "product_id": comp.product_id, "product": product, "state": state, "state_text": state_text,
            "readiness": readiness, "readiness_text": readiness_text, "condition": "USED" if used else "NEW",
            "storage_location": comp.storage_location, "location": loc, "usage": usage,
            "compatibility": compatibility(session, comp.product_id), "price_cents": comp.price_cents}


def inventory(session: Session) -> dict:
    chains = {c["component_id"]: c for c in m.chain_overview(session)}
    items = [item_row(session, c, chains) for c in session.scalars(select(Component).order_by(
        Component.component_type, Component.label))]
    lines = stock.consumable_stock(session)
    for line in lines:
        line["compatibility"] = compatibility(session, line["product_id"])
    history = []
    for d in session.scalars(select(ComponentDisposition).order_by(ComponentDisposition.id.desc()).limit(100)):
        c = session.get(Component, d.component_id)
        history.append({"component_id": c.id, "label": c.label, "disposition": d.disposition,
                        "text": DISPOSITIONS.get(d.disposition, "Record of an undone operation"),
                        "on": d.effective_on, "note": d.note, "voided": bool(d.voided_at),
                        "work_session_id": d.work_session_id})
    return {
        "stock": [line for line in lines if line["tracking_mode"] == "COUNTED"],
        "supplies": [line for line in lines if line["tracking_mode"] == "BULK"],
        "available": [i for i in items if i["state"] in ("NEW_SPARE", "USED_SPARE")],
        "needs_service": [i for i in items if i["state"] == "AWAITING_SERVICE"
                          or i["readiness"] in ("NEEDS_PREPARATION", "WORN")],
        "installed": [i for i in items if i["state"] == "INSTALLED"],
        "out_of_use": [i for i in items if i["state"] in OUT_OF_USE or i["state"] in ("RETIRED", "VOIDED")],
        "shopping_list": stock.shopping_list(session),
        "history": history,
        "sessions": worksessions.recent(session, limit=30),
    }


def replace_options(session: Session, component_id: int) -> dict:
    """Everything the Replace dialog needs, preselected for the outgoing part."""
    comp = get_component(session, component_id)
    inst = open_installation(session, comp.id)
    if not inst:
        raise DomainError(f"{comp.label} is not installed")
    loc = location(session, comp)
    t = COMPONENT_TYPES[comp.component_type]
    chains = {c["component_id"]: c for c in m.chain_overview(session)} if comp.component_type == "CHAIN" else {}
    bike_id = loc.get("bike_id")
    spares = []
    for c in stock.individual_spares(session, comp.component_type, None):
        row = item_row(session, c, chains)
        compat = row["compatibility"]
        row["fit"] = ("VERIFIED" if any(x["bike_id"] == bike_id and x["verified"] for x in compat)
                      else "UNVERIFIED" if any(x["bike_id"] == bike_id for x in compat)
                      else "SAME_PRODUCT" if c.product_id and c.product_id == comp.product_id else "UNKNOWN")
        # parts already on the spare (a stored wheelset with its own wheels, a spare wheel with its tire):
        # the dialog does not carry the old part's children into positions that are taken
        row["mounted"] = [{"component_id": ch.component_id, "label": session.get(Component, ch.component_id).label,
                           "slot": ch.slot} for ch in _open_children(session, c.id)]
        spares.append(row)
    lines = []
    for line in stock.consumable_stock(session):
        if line["component_type"] == comp.component_type and (line["stock"] or {}).get("qty", 0) >= 1:
            compat = compatibility(session, line["product_id"])
            line["fit"] = ("VERIFIED" if any(x["bike_id"] == bike_id and x["verified"] for x in compat)
                           else "UNVERIFIED" if any(x["bike_id"] == bike_id for x in compat)
                           else "SAME_PRODUCT" if line["product_id"] and line["product_id"] == comp.product_id
                           else "UNKNOWN")
            lines.append(line)
    return {"component": {"id": comp.id, "label": comp.label, "component_type": comp.component_type,
                          "type_name": t.name, "product_id": comp.product_id,
                          "product": f"{comp.product.maker or ''} {comp.product.model}".strip() if comp.product else None},
            "location": loc, "suggested_outcome": t.removed_default,
            "outcomes": [{"code": k, "label": v} for k, v in DISPOSITIONS.items()],
            "spares": spares, "stock": lines, "can_same_product": True,
            "children": _children_to_carry(session, comp)}


def _open_children(session: Session, component_id: int) -> list[Installation]:
    return list(session.scalars(select(Installation).where(Installation.parent_component_id == component_id,
                                                           Installation.removed_utc.is_(None),
                                                           Installation.voided_at.is_(None))
                                .order_by(Installation.slot)))


def _children_to_carry(session: Session, comp) -> list[dict]:
    """Parts mounted on the outgoing part, and whether they move to the new one by default. A part whose
    own rule says it should be replaced now (e.g. a quick link that has served its chains) stays behind."""
    out = []
    for i in _open_children(session, comp.id):
        child = session.get(Component, i.component_id)
        due = [r for r in m.component_status(session, child)
               if r.get("trigger") == "PARENT_COUNT" and r["status"] in ("DUE_SOON", "DUE", "OVERDUE")]
        out.append({"component_id": child.id, "label": child.label, "component_type": child.component_type,
                    "type_name": COMPONENT_TYPES[child.component_type].name, "slot": i.slot,
                    "carry_over": not due,
                    "note": due[0]["explanation"] if due else None})
    return out


def move_targets(session: Session, component_id: int) -> list[dict]:
    """Other positions a part can move to on the same bike (e.g. a tire to the other wheel)."""
    comp = get_component(session, component_id)
    loc = location(session, comp)
    if loc["state"] != "INSTALLED" or not loc.get("bike_id"):
        raise NotFound("Part is not installed on a bike")
    t = COMPONENT_TYPES[comp.component_type]
    from bikelog.services.inventory import bike_setup, get_bike
    out = []
    setup = bike_setup(session, get_bike(session, loc["bike_id"]))
    for row in setup:
        if row["component_type"] in t.parent_types and row["component_id"] != loc.get("parent_component_id"):
            for slot in t.slots:
                occ = next((r for r in setup if r["parent_component_id"] == row["component_id"] and r["slot"] == slot), None)
                out.append({"parent_component_id": row["component_id"], "bike_id": None, "slot": slot,
                            "text": f"{row['label']} ({slot.replace('_', ' ').lower()})",
                            "occupied_by": occ["label"] if occ else None})
    if not t.parent_types:
        for slot in t.slots:
            if slot == loc.get("slot"):
                continue
            occ = next((r for r in setup if r["parent_component_id"] is None and r["slot"] == slot), None)
            out.append({"parent_component_id": None, "bike_id": loc["bike_id"], "slot": slot,
                        "text": slot.replace("_", " ").title(), "occupied_by": occ["label"] if occ else None})
    return out


def _slot_text(slot: str) -> str:
    return slot.replace("_", " ").lower()


def mount_targets(session: Session, component_type: str, bike_id: int | None = None) -> dict:
    """Where a new or stored part of this type can go: positions on a bike, or on a part it mounts on
    (wheelset → front/rear wheel → hub → bearings; crankset → chainring; rear derailleur → pulleys), with
    the path to it and what already sits there. With ``bike_id`` only that bike's positions and parts."""
    from bikelog.services.inventory import bike_setup, get_bike
    if component_type not in COMPONENT_TYPES:
        raise DomainError(f"Unknown part type {component_type}")
    t = COMPONENT_TYPES[component_type]
    on_bike = not t.parent_types or component_type in ON_BIKE_TOO
    bikes = [get_bike(session, bike_id)] if bike_id is not None else list(
        session.scalars(select(Bike).where(Bike.status == "ACTIVE").order_by(Bike.name)))
    out: list[dict] = []
    seen: set[int] = set()

    def occupant(parent_id: int | None, bid: int | None, slot: str) -> str | None:
        q = select(Installation).where(Installation.slot == slot, Installation.removed_utc.is_(None),
                                       Installation.voided_at.is_(None))
        q = q.where(Installation.parent_component_id == parent_id) if parent_id is not None \
            else q.where(Installation.bike_id == bid, Installation.parent_component_id.is_(None))
        i = session.scalar(q.limit(1))
        return session.get(Component, i.component_id).label if i else None

    def add_parent(c: Component, group: str, path: list[str]) -> None:
        seen.add(c.id)
        name = f"{' › '.join(path + [c.label])} ({COMPONENT_TYPES[c.component_type].name.lower()})"
        for slot in t.slots:
            out.append({"group": group, "bike_id": None, "parent_component_id": c.id, "slot": slot,
                        "text": name + (f" · {_slot_text(slot)}" if len(t.slots) > 1 else ""),
                        "occupied_by": occupant(c.id, None, slot)})

    for b in bikes:
        if on_bike and not t.slots:      # free positions (bottle cage, accessory): named when installing
            out.append({"group": b.name, "bike_id": b.id, "parent_component_id": None, "slot": None,
                        "text": "On the bike (name the position)", "occupied_by": None})
        if on_bike:
            for slot in t.slots:
                out.append({"group": b.name, "bike_id": b.id, "parent_component_id": None, "slot": slot,
                            "text": f"On the bike · {_slot_text(slot)}", "occupied_by": occupant(None, b.id, slot)})
        rows = bike_setup(session, b)
        labels = {r["component_id"]: r for r in rows}
        for r in rows:
            if r["component_type"] in t.parent_types:
                path, p = [], labels.get(r["parent_component_id"])
                while p is not None:
                    path.insert(0, p["label"])
                    p = labels.get(p["parent_component_id"])
                add_parent(session.get(Component, r["component_id"]), b.name, path)
    if bike_id is None and t.parent_types:
        # parents off the bikes: a stored wheelset's wheels, a spare wheel, a crankset on the shelf
        for c in session.scalars(select(Component).where(Component.component_type.in_(t.parent_types),
                                                         Component.status == "ACTIVE").order_by(Component.label)):
            if c.id in seen or c.disposition == "IN_USE":
                continue
            loc = location(session, c)
            if loc["state"] == "INSTALLED" and loc.get("bike_id"):
                continue          # on a retired bike
            path = []
            inst = open_installation(session, c.id)
            while inst is not None and inst.parent_component_id is not None:
                parent = session.get(Component, inst.parent_component_id)
                path.insert(0, parent.label)
                inst = open_installation(session, parent.id)
            add_parent(c, "Not on a bike (stored)", path)
    return {"component_type": component_type, "on_bike": on_bike, "needs_parent": not on_bike,
            "targets": out}
