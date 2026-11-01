"""What a bike cost: initial cost (its purchase price) and running cost since then.

Running cost is derived from the records every time, never stored:
- parts: the purchase price of each part, counted for the bike it was first installed on (a part mounted
  on a wheel or crankset counts for the bike that part was on). Spares never installed count for no bike.
- stock used: units taken from counted stock or bulk supplies for this bike's parts or maintenance,
  valued at the average purchase price of that stock line (an estimate, marked as such).
- services: the cost entered on maintenance entries, such as a shop fee.
- bundles: parts bought together at one price (e.g. a groupset) count once, with the bundle price, for
  the bike most of their parts were first installed on (services/bundles.py). Their parts have no own price.
Money is counted once: a part drawn from stock has no own price, its value comes from the stock line.
The bike's first frame (DECISIONS 113): with a bike purchase price it came with the bike (its own price, if
any, is shown as included, not counted again); without one, the frame's price is the initial cost (a bike
built up from a frame). A later frame (e.g. a warranty replacement) is a part like any other.
A wheel's built-in parts (wheels, hubs, spokes, rims; BUILT_INTO_WHEEL) without own price inside a priced
wheelset or wheel are included in that
price, not "missing a price". Undone work sessions and voided records are left out.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS
from bikelog.models import (
    Bike, Component, Consumable, ConsumableTxn, Installation, MaintenanceEvent, PurchaseBundle,
)


def _first_bike(session: Session, component_id: int, depth: int = 0) -> int | None:
    """The bike a part was first installed on, following parent parts (wheel, crankset, chain)."""
    inst = session.scalar(select(Installation).where(
        Installation.component_id == component_id, Installation.voided_at.is_(None))
        .order_by(Installation.installed_utc, Installation.id))
    if inst is None or depth > 5:
        return None
    if inst.bike_id is not None:
        return inst.bike_id
    parent = session.scalar(select(Installation).where(
        Installation.component_id == inst.parent_component_id, Installation.voided_at.is_(None),
        Installation.installed_utc <= inst.installed_utc,
        (Installation.removed_utc.is_(None)) | (Installation.removed_utc > inst.installed_utc))
        .order_by(Installation.installed_utc.desc()))
    if parent is None:
        return _first_bike(session, inst.parent_component_id, depth + 1)
    return parent.bike_id if parent.bike_id is not None else _first_bike(session, parent.component_id, depth + 1)


def _unit_cost(session: Session, line_id: int) -> float | None:
    """Average price per unit of a stock line (purchases minus returns)."""
    cents = qty = 0.0
    for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.consumable_id == line_id,
                                                         ConsumableTxn.voided_at.is_(None),
                                                         ConsumableTxn.kind.in_(("PURCHASE", "RETURN")))):
        if t.cost_cents is None or not t.qty:
            continue
        sign = 1 if t.kind == "PURCHASE" else -1
        cents += sign * t.cost_cents
        qty += sign * t.qty
    return cents / qty if qty > 0 else None


# Parts built into a wheel: they come with a wheelset or wheel. Tires, tubes, cassettes and rotors are
# bought on their own and still ask for a price.
BUILT_INTO_WHEEL = ("FRONT_WHEEL", "REAR_WHEEL", "HUB", "HUB_BEARINGS", "SPOKES", "RIM", "RIM_TAPE")


def _in_priced_parent(session: Session, component_id: int, live_bundles, depth: int = 0) -> bool:
    """True when the part sits (or sat) inside a part that has a price or a live bundle, at any level
    (spokes on a wheel of a priced wheelset)."""
    if depth > 5:
        return False
    parents = set(session.scalars(select(Installation.parent_component_id).where(
        Installation.component_id == component_id, Installation.voided_at.is_(None),
        Installation.parent_component_id.is_not(None))))
    for pid in parents:
        parent = session.get(Component, pid)
        if parent is None or parent.disposition == "VOIDED":
            continue
        if parent.price_cents is not None or parent.bundle_id in live_bundles:
            return True
        if _in_priced_parent(session, pid, live_bundles, depth + 1):
            return True
    return False


def bike_attribution(session: Session) -> dict[int, int | None]:
    return {c.id: _first_bike(session, c.id) for c in session.scalars(
        select(Component).where(Component.disposition != "VOIDED"))}


def first_frame(session: Session, bike: Bike) -> Component | None:
    """The frame first installed on this bike (the one it was bought or built with)."""
    return session.scalar(select(Component).join(Installation, Installation.component_id == Component.id).where(
        Installation.bike_id == bike.id, Installation.voided_at.is_(None), Component.component_type == "FRAME",
        Component.disposition != "VOIDED").order_by(Installation.installed_utc, Installation.id).limit(1))


def current_frame(session: Session, bike: Bike) -> Component | None:
    return session.scalar(select(Component).join(Installation, Installation.component_id == Component.id).where(
        Installation.bike_id == bike.id, Installation.voided_at.is_(None), Installation.removed_utc.is_(None),
        Component.component_type == "FRAME").limit(1))


def bike_costs(session: Session, bike: Bike, *, attribution: dict[int, int | None] | None = None,
               with_items: bool = True) -> dict:
    first_bike = attribution if attribution is not None else bike_attribution(session)
    original = first_frame(session, bike)
    frame_initial = (bike.purchase_price_cents is None and original is not None
                     and original.price_cents is not None and not original.bundle_id)
    items: list[dict] = []
    unpriced: list[str] = []
    from bikelog.services import bundles as bundles_svc
    live_bundles = {b.id: b for b in session.scalars(select(PurchaseBundle).where(PurchaseBundle.voided_at.is_(None)))}
    unpriced_bundles = 0
    for b in live_bundles.values():
        comps = [c for c in bundles_svc.members(session, b) if c.disposition != "VOIDED"]
        if bundles_svc.bike_of(b, comps, first_bike) != bike.id:
            continue
        if b.price_cents is None:
            unpriced_bundles += 1
            continue
        # a groupset bought as one: links to the groupset page; another bundle to its first part
        from bikelog.services.assemblies import in_groupset
        gs = any(in_groupset(c.component_type) for c in comps)
        items.append({"kind": "BUNDLE", "date": b.purchased_on, "bundle_id": b.id, "cents": b.price_cents,
                      "text": f"{b.name} ({len(comps)} parts{', ' + b.merchant if b.merchant else ''})",
                      "estimated": False, "groupset": gs,
                      "component_id": None if gs or not comps else comps[0].id})
    for cid, bid in first_bike.items():
        if bid != bike.id:
            continue
        c = session.get(Component, cid)
        if c.bundle_id in live_bundles:
            continue                      # priced by its bundle
        if original is not None and c.id == original.id:
            continue                      # the bike's first frame: initial cost, or included in the bike price
        if c.price_cents is not None:
            items.append({"kind": "PART", "date": c.purchase_date, "text": c.label, "component_id": c.id,
                          "cents": c.price_cents, "estimated": False})
        elif (not c.from_stock_txn_id and c.component_type not in ("FRAME", "FORK")
              and not (c.component_type in BUILT_INTO_WHEEL and _in_priced_parent(session, c.id, live_bundles))):
            unpriced.append(c.label)      # a frame and fork without own price came with the bike; a part
            # inside a priced wheelset/wheel/bundle part is included in that price

    events = list(session.scalars(select(MaintenanceEvent).where(MaintenanceEvent.voided_at.is_(None),
                                                                 MaintenanceEvent.bike_id == bike.id)))
    for e in events:
        if e.cost_cents:
            name = ACTIONS[e.action_code].name if e.action_code in ACTIONS else e.action_code
            items.append({"kind": "SERVICE", "date": e.performed_on, "text": name, "event_id": e.id,
                          "cents": e.cost_cents, "estimated": False})

    event_ids = {e.id for e in events}
    unit_costs: dict[int, float | None] = {}
    unvalued = 0
    for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.kind == "USE",
                                                         ConsumableTxn.voided_at.is_(None))):
        mine = (t.maintenance_event_id in event_ids) or (t.component_id is not None
                                                          and first_bike.get(t.component_id) == bike.id)
        if not mine or not t.qty:
            continue
        if t.consumable_id not in unit_costs:
            unit_costs[t.consumable_id] = _unit_cost(session, t.consumable_id)
        unit = unit_costs[t.consumable_id]
        if unit is None:
            unvalued += 1
            continue
        line = session.get(Consumable, t.consumable_id)
        items.append({"kind": "STOCK", "date": t.occurred_on, "text": f"{t.qty:g} {line.unit} {line.name}",
                      "cents": round(unit * t.qty), "estimated": True})

    def total(kind: str) -> int:
        return sum(i["cents"] for i in items if i["kind"] == kind)

    running = total("PART") + total("BUNDLE") + total("STOCK") + total("SERVICE")
    initial = original.price_cents if frame_initial else bike.purchase_price_cents
    frame = current_frame(session, bike) or original
    frame_row = None
    if frame is not None:
        if frame.id == (original.id if original else None):
            counted = ("INITIAL" if frame_initial else "INCLUDED" if bike.purchase_price_cents is not None
                       else "NO_PRICE")
        else:
            counted = "PART" if frame.price_cents is not None and first_bike.get(frame.id) == bike.id else (
                "NO_PRICE" if frame.price_cents is None else "OTHER_BIKE")
        frame_row = {"component_id": frame.id, "label": frame.label, "price_cents": frame.price_cents,
                     "purchase_date": frame.purchase_date, "shop": frame.shop, "counted": counted}
    out = {
        "initial_cents": initial, "initial_source": "FRAME" if frame_initial else "BIKE" if initial is not None else None,
        "frame": frame_row,
        "purchase_date": original.purchase_date if frame_initial else bike.purchase_date,
        "parts_cents": total("PART"), "bundles_cents": total("BUNDLE"), "stock_cents": total("STOCK"),
        "services_cents": total("SERVICE"), "unpriced_bundles": unpriced_bundles,
        "running_cents": running, "total_cents": (initial or 0) + running,
        "estimated": any(i["estimated"] for i in items),
        "unpriced_parts": len(unpriced), "unpriced_labels": sorted(unpriced), "unvalued_stock_uses": unvalued,
        "initial_known": initial is not None,
    }
    if with_items:
        items.sort(key=lambda i: (i["date"] or ""), reverse=True)
        out["items"] = items
    return out


def per_km(costs: dict, total_km: float) -> int | None:
    return round(costs["total_cents"] / total_km) if total_km and costs["total_cents"] else None
