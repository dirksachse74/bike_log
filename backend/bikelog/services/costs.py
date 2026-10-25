"""What a bike cost: initial cost (its purchase price) and running cost since then.

Running cost is derived from the records every time, never stored:
- parts: the purchase price of each part, counted for the bike it was first installed on (a part mounted
  on a wheel or crankset counts for the bike that part was on). Spares never installed count for no bike.
- stock used: units taken from counted stock or bulk supplies for this bike's parts or maintenance,
  valued at the average purchase price of that stock line (an estimate, marked as such).
- services: the cost entered on maintenance entries, such as a shop fee.
Money is counted once: a part drawn from stock has no own price, its value comes from the stock line.
Undone work sessions and voided records are left out.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS
from bikelog.models import Bike, Component, Consumable, ConsumableTxn, Installation, MaintenanceEvent


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


def bike_attribution(session: Session) -> dict[int, int | None]:
    return {c.id: _first_bike(session, c.id) for c in session.scalars(
        select(Component).where(Component.disposition != "VOIDED"))}


def bike_costs(session: Session, bike: Bike, *, attribution: dict[int, int | None] | None = None,
               with_items: bool = True) -> dict:
    first_bike = attribution if attribution is not None else bike_attribution(session)
    items: list[dict] = []
    unpriced: list[str] = []
    for cid, bid in first_bike.items():
        if bid != bike.id:
            continue
        c = session.get(Component, cid)
        if c.price_cents is not None:
            items.append({"kind": "PART", "date": c.purchase_date, "text": c.label, "component_id": c.id,
                          "cents": c.price_cents, "estimated": False})
        elif not c.from_stock_txn_id:
            unpriced.append(c.label)

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

    running = total("PART") + total("STOCK") + total("SERVICE")
    initial = bike.purchase_price_cents
    out = {
        "initial_cents": initial, "purchase_date": bike.purchase_date,
        "parts_cents": total("PART"), "stock_cents": total("STOCK"), "services_cents": total("SERVICE"),
        "running_cents": running, "total_cents": (initial or 0) + running,
        "estimated": any(i["estimated"] for i in items),
        "unpriced_parts": len(unpriced), "unvalued_stock_uses": unvalued,
        "initial_known": initial is not None,
    }
    if with_items:
        items.sort(key=lambda i: (i["date"] or ""), reverse=True)
        out["items"] = items
        out["unpriced_labels"] = sorted(unpriced)
    return out


def per_km(costs: dict, total_km: float) -> int | None:
    return round(costs["total_cents"] / total_km) if total_km and costs["total_cents"] else None
