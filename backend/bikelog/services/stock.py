"""Stock: counted spare parts and supplies, and bulk supplies. Individual items are components.

Three tracking modes
* Individual item (component): own identity, installation and usage history (chain, tire, tube, rotor).
* Counted stock (consumable, COUNTED): whole units available per product (spare pad sets, tubes,
  quick links, patches, coin cells). Installing one creates an individual component in the same
  transaction as the stock USE, so one item is never both "available stock" and "installed".
* Bulk supply (consumable, BULK): wax, sealant, fluid, grease; amounts used are optional.

Purchases, returns to the shop, corrections and uses are separate transactions. Only purchases (and
returns) carry money, so linking a use to a maintenance session never counts a cost twice.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, STOCK_UNITS, TRACKING_MODES
from bikelog.models import Component, Consumable, ConsumableTxn, Product
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import create_component, open_installation

TXN_SIGN = {"PURCHASE": 1, "ADJUST": 1, "USE": -1, "RETURN": -1}


def get(session: Session, consumable_id: int) -> Consumable:
    c = session.get(Consumable, consumable_id)
    if not c:
        raise NotFound("Stock item not found")
    return c


def _product_name(session: Session, product_id: int | None) -> str | None:
    p = session.get(Product, product_id) if product_id else None
    return f"{p.maker or ''} {p.model}".strip() if p else None


def add_consumable(session: Session, *, kind: str = "OTHER", name: str | None = None, maker: str | None = None,
                   unit: str | None = None, track_stock: bool = False, notes: str | None = None,
                   tracking_mode: str = "BULK", component_type: str | None = None, product_id: int | None = None,
                   unit_note: str | None = None, storage_location: str | None = None, min_stock: float | None = None,
                   container_size: float | None = None) -> Consumable:
    """A stock line. For spare parts pass component_type (and ideally product_id); name, unit and
    unit note then default from the product and catalog.STOCK_UNITS."""
    if tracking_mode not in TRACKING_MODES:
        raise DomainError(f"tracking_mode must be one of {', '.join(TRACKING_MODES)}")
    if component_type is not None:
        if component_type not in COMPONENT_TYPES:
            raise DomainError(f"Unknown component type {component_type!r}")
        tracking_mode, kind = "COUNTED", "PART"
    if product_id is not None:
        prod = session.get(Product, product_id)
        if not prod:
            raise NotFound("Product not found")
        if component_type and prod.component_type != component_type:
            raise DomainError(f"{prod.model} is a {prod.component_type}, not a {component_type}")
        component_type = component_type or prod.component_type
        tracking_mode, kind = "COUNTED", "PART"
    if not name:
        if not component_type:
            raise DomainError("Name the product")
        name = " — ".join(x for x in (COMPONENT_TYPES[component_type].name, _product_name(session, product_id)) if x)
    default_unit, default_note = STOCK_UNITS.get(component_type or "", ("pcs" if tracking_mode == "COUNTED" else "ml", None))
    if session.scalar(select(Consumable).where(Consumable.name == name)):
        raise DomainError(f"{name!r} already exists")
    if min_stock is not None and min_stock < 0:
        raise DomainError("Minimum stock cannot be negative")
    c = Consumable(kind=kind, name=name, maker=maker, unit=unit or default_unit,
                   track_stock=True if tracking_mode == "COUNTED" else track_stock, notes=notes,
                   tracking_mode=tracking_mode, component_type=component_type, product_id=product_id,
                   unit_note=unit_note or default_note, storage_location=storage_location, min_stock=min_stock,
                   container_size=container_size)
    session.add(c)
    session.flush()
    return c


def update_consumable(session: Session, consumable_id: int, **fields) -> Consumable:
    c = get(session, consumable_id)
    for k in ("name", "maker", "unit", "unit_note", "storage_location", "min_stock", "notes", "container_size"):
        if k in fields:
            setattr(c, k, fields[k])
    session.flush()
    return c


def level(session: Session, c: Consumable) -> dict:
    txns = list(session.scalars(select(ConsumableTxn).where(ConsumableTxn.consumable_id == c.id,
                                                            ConsumableTxn.voided_at.is_(None))))
    known = all(t.qty is not None for t in txns)
    qty = sum((t.qty or 0) * TXN_SIGN[t.kind] for t in txns)
    return {"qty": round(qty, 3), "known": known, "txns": txns}


def _whole(c: Consumable, qty: float | None, what: str) -> float:
    if qty is None:
        if c.tracking_mode == "COUNTED":
            raise DomainError(f"Say how many {c.unit}s were {what}")
        return qty
    if c.tracking_mode == "COUNTED" and float(qty) != int(qty):
        raise DomainError(f"{c.name} is counted in whole {c.unit}s")
    return qty


def consumable_txn(session: Session, consumable_id: int, *, kind: str, qty: float | None, on: str,
                   cost_cents: int | None = None, note: str | None = None, packages: int | None = None,
                   work_session_id: int | None = None) -> ConsumableTxn:
    """PURCHASE (+), RETURN to the shop (−), ADJUST (signed correction after a count), USE (−)."""
    c = get(session, consumable_id)
    if kind not in TXN_SIGN:
        raise DomainError(f"kind must be one of {', '.join(TXN_SIGN)}")
    if kind == "USE":
        return use(session, consumable_id, qty=qty, on=on, note=note, work_session_id=work_session_id)
    qty = _whole(c, qty, {"PURCHASE": "bought", "RETURN": "returned", "ADJUST": "corrected"}[kind])
    if kind in ("PURCHASE", "RETURN") and qty is not None and qty <= 0:
        raise DomainError("Quantity must be positive")
    if kind == "RETURN" and c.track_stock:
        have = level(session, c)["qty"]
        if qty > have:
            raise DomainError(f"Only {have:g} {c.unit}(s) in stock; cannot return {qty:g}")
    if kind == "ADJUST" and not note:
        raise DomainError("Say why the stock is corrected (e.g. 'counted drawer')")
    t = ConsumableTxn(consumable_id=c.id, kind=kind, qty=qty, occurred_on=on[:10], packages=packages,
                      cost_cents=cost_cents if kind in ("PURCHASE", "RETURN") else None, note=note,
                      work_session_id=work_session_id)
    session.add(t)
    session.flush()
    return t


def use(session: Session, consumable_id: int, *, qty: float | None, on: str, note: str | None = None,
        work_session_id: int | None = None, maintenance_event_id: int | None = None,
        component_id: int | None = None) -> ConsumableTxn:
    """Use supplies. Counted stock needs a whole quantity and enough stock; bulk amounts may be unknown."""
    c = get(session, consumable_id)
    qty = _whole(c, qty, "used")
    if qty is not None and qty <= 0:
        raise DomainError("Quantity used must be positive")
    if c.tracking_mode == "COUNTED":
        have = level(session, c)["qty"]
        if qty > have:
            raise DomainError(f"Only {have:g} {c.unit}(s) of {c.name} in stock. Record the purchase or a stock "
                              "correction first.")
    t = ConsumableTxn(consumable_id=c.id, kind="USE", qty=qty, occurred_on=on[:10], note=note,
                      work_session_id=work_session_id, maintenance_event_id=maintenance_event_id,
                      component_id=component_id)
    session.add(t)
    session.flush()
    return t


def draw_component(session: Session, consumable_id: int, *, on: str, label: str | None = None,
                   work_session_id: int | None = None) -> Component:
    """Take one unit out of counted stock and give it its own identity (to install it)."""
    c = get(session, consumable_id)
    if c.tracking_mode != "COUNTED" or not c.component_type:
        raise DomainError(f"{c.name} is not stock of a part type")
    txn = use(session, c.id, qty=1, on=on, note="taken from stock to install", work_session_id=work_session_id)
    comp = create_component(session, component_type=c.component_type, label=label or _stock_label(session, c),
                            product_id=c.product_id, prior_usage="NEW", work_session_id=work_session_id,
                            from_stock_txn_id=txn.id)
    txn.component_id = comp.id
    session.flush()
    return comp


def _stock_label(session: Session, c: Consumable) -> str:
    base = COMPONENT_TYPES[c.component_type].name
    if c.product_id:
        p = session.get(Product, c.product_id)
        base = f"{base} {p.model}"
    n = 1
    while session.scalar(select(Component).where(Component.component_type == c.component_type,
                                                 Component.label == f"{base} #{n}")):
        n += 1
    return f"{base} #{n}"


def individual_spares(session: Session, component_type: str | None, product_id: int | None) -> list[Component]:
    """Individually tracked parts off the bike and ready (used spares, or new ones with an identity)."""
    q = select(Component).where(Component.status == "ACTIVE", Component.disposition == "STORED")
    if component_type:
        q = q.where(Component.component_type == component_type)
    if product_id:
        q = q.where(Component.product_id == product_id)
    return [c for c in session.scalars(q.order_by(Component.label)) if not open_installation(session, c.id)]


def consumable_stock(session: Session) -> list[dict]:
    out = []
    for c in session.scalars(select(Consumable).order_by(Consumable.tracking_mode.desc(), Consumable.kind,
                                                         Consumable.name)):
        lv = level(session, c)
        txns = lv["txns"]
        stock = {"qty": lv["qty"], "known": lv["known"]} if c.track_stock else None
        individual = individual_spares(session, c.component_type, c.product_id) if c.product_id else []
        available = (lv["qty"] if c.track_stock else None)
        total = None if available is None else available + len(individual)
        low = c.min_stock is not None and total is not None and total < c.min_stock
        out.append({"id": c.id, "kind": c.kind, "name": c.name, "maker": c.maker, "unit": c.unit,
                    "unit_note": c.unit_note, "tracking_mode": c.tracking_mode, "component_type": c.component_type,
                    "product_id": c.product_id, "product": _product_name(session, c.product_id),
                    "storage_location": c.storage_location, "min_stock": c.min_stock,
                    "container_size": c.container_size, "track_stock": c.track_stock, "stock": stock,
                    "individual_spares": [{"id": x.id, "label": x.label} for x in individual],
                    "available_total": total, "low": low,
                    "purchases": sum(1 for t in txns if t.kind == "PURCHASE"),
                    "uses": sum(1 for t in txns if t.kind == "USE"),
                    "spent_cents": sum((t.cost_cents or 0) * (1 if t.kind == "PURCHASE" else -1)
                                       for t in txns if t.kind in ("PURCHASE", "RETURN")),
                    "notes": c.notes})
    return out


def shopping_list(session: Session) -> list[dict]:
    """Suggestions only: stock lines below their optional minimum."""
    out = []
    for row in consumable_stock(session):
        if row["low"]:
            need = row["min_stock"] - row["available_total"]
            out.append({"consumable_id": row["id"], "name": row["name"], "unit": row["unit"],
                        "available": row["available_total"], "min_stock": row["min_stock"],
                        "suggested_qty": need if row["tracking_mode"] != "COUNTED" else int(-(-need // 1)),
                        "text": f"Buy {need:g} {row['unit']}(s) of {row['name']}: {row['available_total']:g} "
                                f"available, minimum {row['min_stock']:g}"})
    return out


def txn_history(session: Session, consumable_id: int) -> list[dict]:
    return [{"id": t.id, "kind": t.kind, "qty": t.qty, "packages": t.packages, "on": t.occurred_on,
             "cost_cents": t.cost_cents, "note": t.note, "component_id": t.component_id,
             "work_session_id": t.work_session_id, "maintenance_event_id": t.maintenance_event_id,
             "voided": bool(t.voided_at)}
            for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.consumable_id == consumable_id)
                                     .order_by(ConsumableTxn.occurred_on.desc(), ConsumableTxn.id.desc()))]
