"""Purchase bundles: parts bought together at one price, one shop, one date (e.g. a whole groupset).

Money rules (see costs.py and DECISIONS 51):
* The bundle price is the only price: member parts carry no own price, so nothing is counted twice.
* The bundle counts once, for the bike most of its parts were first installed on.
* A per-part *share* is shown for information only and marked as an estimate: split by the products'
  reference prices where known, otherwise evenly. It never enters the running cost.
* Parts replaced later (pads, rotor, chain) are new parts with their own price and no bundle. The original
  parts stay members, retired or stored, so the bundle shows what was bought and what is still in use.
Bundles are never deleted; one entered by mistake is voided and its parts can then be priced on their own.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES
from bikelog.models import Bike, Component, PurchaseBundle
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import location
from bikelog.timeutil import utc_now


def get(session: Session, bundle_id: int) -> PurchaseBundle:
    b = session.get(PurchaseBundle, bundle_id)
    if not b:
        raise NotFound("Bundle not found")
    return b


def active(b: PurchaseBundle | None) -> bool:
    return b is not None and b.voided_at is None


def _check_price(cents: int | None) -> None:
    if cents is not None and cents < 0:
        raise DomainError("A price cannot be negative")


def _check_member(session: Session, comp: Component, bundle: PurchaseBundle) -> None:
    if comp.disposition == "VOIDED":
        raise DomainError(f"{comp.label} is the record of an undone operation")
    if comp.bundle_id and comp.bundle_id != bundle.id and active(session.get(PurchaseBundle, comp.bundle_id)):
        raise DomainError(f"{comp.label} already belongs to another bundle")
    if comp.price_cents is not None:
        raise DomainError(f"{comp.label} has its own price (€{comp.price_cents / 100:,.2f}). A part is priced either "
                          "on its own or as part of a bundle: remove its price first, or leave it out.")
    if comp.from_stock_txn_id:
        raise DomainError(f"{comp.label} came from stock; its cost belongs to that stock purchase")


def create(session: Session, *, name: str, component_ids: list[int], merchant: str | None = None,
           purchased_on: str | None = None, price_cents: int | None = None, notes: str | None = None,
           work_session_id: int | None = None) -> PurchaseBundle:
    name = (name or "").strip()
    if not name:
        raise DomainError("Give the bundle a name, e.g. 'Ultegra Di2 R8100 groupset'")
    if not component_ids:
        raise DomainError("Pick the parts that were bought together")
    _check_price(price_cents)
    b = PurchaseBundle(name=name, merchant=(merchant or "").strip() or None, purchased_on=purchased_on,
                       price_cents=price_cents, notes=notes, work_session_id=work_session_id)
    session.add(b)
    session.flush()
    add_members(session, b.id, component_ids)
    return b


def update(session: Session, bundle_id: int, **fields) -> PurchaseBundle:
    b = get(session, bundle_id)
    if not active(b):
        raise DomainError("This bundle was voided")
    if "price_cents" in fields:
        _check_price(fields["price_cents"])
    if "name" in fields and not (fields["name"] or "").strip():
        raise DomainError("The bundle needs a name")
    for k in ("name", "merchant", "purchased_on", "price_cents", "notes"):
        if k in fields:
            setattr(b, k, fields[k])
    session.flush()
    return b


def add_members(session: Session, bundle_id: int, component_ids: list[int]) -> PurchaseBundle:
    b = get(session, bundle_id)
    if not active(b):
        raise DomainError("This bundle was voided")
    for cid in dict.fromkeys(component_ids):
        comp = session.get(Component, cid)
        if comp is None:
            raise NotFound(f"Part {cid} not found")
        _check_member(session, comp, b)
        comp.bundle_id = b.id
    session.flush()
    return b


def remove_member(session: Session, bundle_id: int, component_id: int) -> PurchaseBundle:
    """Only for a part added by mistake. A part that was bought in the bundle and later replaced stays a
    member (replacing it does not change what was bought)."""
    b = get(session, bundle_id)
    comp = session.get(Component, component_id)
    if comp is None or comp.bundle_id != b.id:
        raise DomainError("That part is not in this bundle")
    comp.bundle_id = None
    session.flush()
    return b


def void(session: Session, bundle_id: int, reason: str) -> PurchaseBundle:
    b = get(session, bundle_id)
    if not reason:
        raise DomainError("Say why this bundle is wrong")
    if not b.voided_at:
        b.voided_at, b.void_reason = utc_now(), reason
        session.flush()
    return b


def members(session: Session, b: PurchaseBundle) -> list[Component]:
    return list(session.scalars(select(Component).where(Component.bundle_id == b.id)
                                .order_by(Component.component_type, Component.label)))


def shares(session: Session, b: PurchaseBundle, comps: list[Component] | None = None) -> dict[int, int]:
    """Estimated share of the bundle price per part (information only). Parts with a reference price are
    weighted by it; parts without one get the average weight; rounding goes to the largest share."""
    comps = comps if comps is not None else [c for c in members(session, b) if c.disposition != "VOIDED"]
    if b.price_cents is None or not comps:
        return {}
    ref = {c.id: (c.product.list_price_cents if c.product and c.product.list_price_cents else None) for c in comps}
    known = [v for v in ref.values() if v]
    default = (sum(known) / len(known)) if known else 1.0
    weights = {cid: float(v or default) for cid, v in ref.items()}
    total = sum(weights.values())
    out = {cid: int(b.price_cents * w / total) for cid, w in weights.items()}
    out[max(weights, key=lambda k: weights[k])] += b.price_cents - sum(out.values())
    return out


def bike_of(b: PurchaseBundle, comps: list[Component], first_bike: dict[int, int | None]) -> int | None:
    """The bike the bundle counts for: where most of its parts were first installed."""
    votes = Counter(first_bike.get(c.id) for c in comps if first_bike.get(c.id) is not None)
    return votes.most_common(1)[0][0] if votes else None


def row(session: Session, b: PurchaseBundle, first_bike: dict[int, int | None] | None = None) -> dict:
    from bikelog.services.costs import bike_attribution
    comps = [c for c in members(session, b) if c.disposition != "VOIDED"]
    first_bike = first_bike if first_bike is not None else bike_attribution(session)
    share = shares(session, b, comps)
    bike_id = bike_of(b, comps, first_bike)
    bike = session.get(Bike, bike_id) if bike_id else None
    rows = []
    for c in comps:
        loc = location(session, c)
        rows.append({"component_id": c.id, "label": c.label, "component_type": c.component_type,
                     "type_name": COMPONENT_TYPES[c.component_type].name if c.component_type in COMPONENT_TYPES
                     else c.component_type, "status": c.status, "state": loc["state"], "where": loc["text"],
                     "in_use": loc["state"] == "INSTALLED", "share_cents": share.get(c.id)})
    has_ref = any(c.product and c.product.list_price_cents for c in comps)
    return {"id": b.id, "name": b.name, "merchant": b.merchant, "purchased_on": b.purchased_on,
            "price_cents": b.price_cents, "notes": b.notes, "voided": bool(b.voided_at), "void_reason": b.void_reason,
            "bike_id": bike_id, "bike": bike.name if bike else None, "members": rows,
            "in_use": sum(1 for r in rows if r["in_use"]), "member_count": len(rows),
            "share_basis": "reference prices" if has_ref else "split evenly"}


def list_rows(session: Session, *, bike_id: int | None = None, include_voided: bool = False) -> list[dict]:
    from bikelog.services.costs import bike_attribution
    first_bike = bike_attribution(session)
    q = select(PurchaseBundle).order_by(PurchaseBundle.purchased_on.desc(), PurchaseBundle.id.desc())
    if not include_voided:
        q = q.where(PurchaseBundle.voided_at.is_(None))
    out = [row(session, b, first_bike) for b in session.scalars(q)]
    return [r for r in out if bike_id is None or r["bike_id"] == bike_id]


def candidates(session: Session, bike_id: int | None = None) -> list[dict]:
    """Parts that could join a bundle: no own price, not from stock, not in an active bundle."""
    out = []
    for c in session.scalars(select(Component).where(Component.price_cents.is_(None),
                                                     Component.from_stock_txn_id.is_(None),
                                                     Component.disposition != "VOIDED")
                             .order_by(Component.component_type, Component.label)):
        if c.bundle_id and active(session.get(PurchaseBundle, c.bundle_id)):
            continue
        loc = location(session, c)
        if bike_id is not None and loc.get("bike_id") != bike_id:
            continue
        out.append({"component_id": c.id, "label": c.label, "component_type": c.component_type,
                    "type_name": COMPONENT_TYPES[c.component_type].name, "where": loc["text"],
                    "purchase_date": c.purchase_date})
    return out
