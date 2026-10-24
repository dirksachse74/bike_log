"""Bikes, product models, physical components and installation history."""
from __future__ import annotations

import json

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, DISPOSITIONS, OUT_OF_USE
from bikelog.models import (
    Bike, Component, ComponentDisposition, Installation, Product, UsageAdjustment, UsageContribution,
)
from bikelog.services import allocation, settings
from bikelog.services.errors import Conflict, DomainError, NotFound, Protected
from bikelog.timeutil import FAR_FUTURE, parse_when, utc_now


# ---------------------------------------------------------------- lookups

def get_bike(session: Session, bike_id: int) -> Bike:
    b = session.get(Bike, bike_id)
    if not b:
        raise NotFound(f"Bike {bike_id} not found")
    return b


def get_component(session: Session, component_id: int) -> Component:
    c = session.get(Component, component_id)
    if not c:
        raise NotFound(f"Component {component_id} not found")
    return c


def _reallocate(session: Session) -> None:
    allocation.rebuild_all(session, settings.tz(session))


# ---------------------------------------------------------------- bikes

def create_bike(session: Session, *, name: str, maker: str | None = None, model: str | None = None,
                year: int | None = None, strava_gear_id: str | None = None, notes: str | None = None,
                starting_km: float | None = None, starting_date: str | None = None,
                starting_is_estimate: bool = False) -> Bike:
    name = (name or "").strip()
    if not name:
        raise DomainError("A bike needs a name")
    if session.scalar(select(Bike).where(func.lower(Bike.name) == name.lower())):
        raise Conflict(f"A bike called {name!r} already exists")
    bike = Bike(name=name, maker=maker, model=model, year=year, strava_gear_id=strava_gear_id or None, notes=notes)
    session.add(bike)
    session.flush()
    if starting_km is not None:
        set_starting_usage(session, bike_id=bike.id, km=starting_km, effective=starting_date,
                           is_estimate=starting_is_estimate)
    return bike


def update_bike(session: Session, bike_id: int, **fields) -> Bike:
    bike = get_bike(session, bike_id)
    for k in ("name", "maker", "model", "year", "strava_gear_id", "notes"):
        if k in fields:
            setattr(bike, k, fields[k] or None if k != "name" else fields[k])
    try:
        session.flush()
    except IntegrityError as e:
        raise Conflict("Name or Strava gear id already used by another bike") from e
    return bike


def retire_bike(session: Session, bike_id: int) -> Bike:
    bike = get_bike(session, bike_id)
    bike.status = "RETIRED"
    session.flush()
    return bike


# ---------------------------------------------------------------- products & components

def create_product(session: Session, *, component_type: str, model: str, maker: str | None = None,
                   specs: dict | None = None, spec_source: str | None = None, spec_version: str | None = None,
                   notes: str | None = None) -> Product:
    _check_type(component_type)
    p = Product(component_type=component_type, maker=maker, model=model, specs_json=json.dumps(specs or {}),
                spec_source=spec_source, spec_version=spec_version, notes=notes)
    session.add(p)
    session.flush()
    return p


def _check_type(code: str) -> None:
    if code not in COMPONENT_TYPES:
        raise DomainError(f"Unknown component type {code!r}")


def create_component(session: Session, *, component_type: str, label: str, product_id: int | None = None,
                     prior_usage: str = "UNKNOWN", serial_number: str | None = None,
                     purchase_date: str | None = None, price_cents: int | None = None, notes: str | None = None,
                     specs: dict | None = None, starting_km: float | None = None, starting_date: str | None = None,
                     starting_is_estimate: bool = False, work_session_id: int | None = None,
                     from_stock_txn_id: int | None = None, storage_location: str | None = None) -> Component:
    """Only type and label are required; everything else (serial number, specs) can be added later.
    With a work session, price_cents is that session's purchase of this item."""
    _check_type(component_type)
    label = (label or "").strip()
    if not label:
        raise DomainError("A component needs a name/label, e.g. 'Chain A'")
    if prior_usage not in ("NEW", "UNKNOWN", "RECORDED"):
        raise DomainError("prior_usage must be NEW, UNKNOWN or RECORDED")
    if product_id is not None:
        prod = session.get(Product, product_id)
        if not prod:
            raise NotFound(f"Product {product_id} not found")
        if prod.component_type != component_type:
            raise DomainError(f"Product {prod.model!r} is a {prod.component_type}, not a {component_type}")
    if session.scalar(select(Component).where(Component.component_type == component_type,
                                              func.lower(Component.label) == label.lower())):
        raise Conflict(f"There is already a {COMPONENT_TYPES[component_type].name.lower()} labelled {label!r}")
    comp = Component(component_type=component_type, label=label, product_id=product_id, prior_usage=prior_usage,
                     serial_number=serial_number, purchase_date=purchase_date, price_cents=price_cents, notes=notes,
                     specs_json=json.dumps(specs or {}), disposition="STORED",
                     purchase_session_id=work_session_id,
                     from_stock_txn_id=from_stock_txn_id, storage_location=storage_location)
    session.add(comp)
    session.flush()
    if starting_km is not None:
        set_starting_usage(session, component_id=comp.id, km=starting_km, effective=starting_date,
                           is_estimate=starting_is_estimate)
    return comp


def update_component(session: Session, component_id: int, **fields) -> Component:
    comp = get_component(session, component_id)
    for k in ("label", "serial_number", "purchase_date", "price_cents", "notes", "product_id", "prior_usage",
              "storage_location"):
        if k in fields:
            setattr(comp, k, fields[k])
    if "specs" in fields:
        comp.specs_json = json.dumps(fields["specs"] or {})
    try:
        session.flush()
    except IntegrityError as e:
        raise Conflict("Another component of this type already has that label") from e
    return comp


def set_starting_usage(session: Session, *, km: float, effective: str | None, is_estimate: bool,
                       component_id: int | None = None, bike_id: int | None = None, note: str | None = None
                       ) -> UsageAdjustment:
    """Starting mileage as of an effective date. Rides before that date are inside this value."""
    if km < 0:
        raise DomainError("Starting mileage cannot be negative")
    tz = settings.tz(session)
    w = parse_when(effective or utc_now(), tz)
    q = select(UsageAdjustment).where(UsageAdjustment.kind == "STARTING", UsageAdjustment.voided_at.is_(None))
    q = q.where(UsageAdjustment.component_id == component_id) if component_id else q.where(UsageAdjustment.bike_id == bike_id)
    for old in session.scalars(q):
        old.voided_at = utc_now()
    adj = UsageAdjustment(component_id=component_id, bike_id=bike_id, kind="STARTING", effective_at=w.raw,
                          effective_utc=w.utc, km=km, is_estimate=is_estimate, note=note)
    session.add(adj)
    if component_id:
        get_component(session, component_id).prior_usage = "RECORDED"
    session.flush()
    if component_id:
        _reallocate(session)
    return adj


def add_correction(session: Session, component_id: int, km: float, effective: str, note: str) -> UsageAdjustment:
    if not note:
        raise DomainError("A mileage correction needs a reason")
    w = parse_when(effective, settings.tz(session))
    adj = UsageAdjustment(component_id=component_id, kind="CORRECTION", effective_at=w.raw, effective_utc=w.utc,
                          km=km, is_estimate=False, note=note)
    session.add(adj)
    session.flush()
    return adj


def set_disposition(session: Session, component_id: int, disposition: str, *, on: str,
                    note: str | None = None, work_session_id: int | None = None) -> Component:
    """Record what happened to a part that is off the bike. Removes it first if it is still installed.
    RETIRED, DISCARDED and SOLD take it out of use; the record and its history always stay."""
    if disposition not in DISPOSITIONS:
        raise DomainError(f"Choose one of: {', '.join(DISPOSITIONS)}")
    comp = get_component(session, component_id)
    on_date = parse_when(on, settings.tz(session)).local_date
    if open_installation(session, component_id):
        remove(session, component_id, at=on, reason=note or DISPOSITIONS[disposition].lower(), outcome=disposition,
               work_session_id=work_session_id)
        return comp
    if comp.disposition == disposition and comp.status == ("RETIRED" if disposition in OUT_OF_USE else "ACTIVE"):
        return comp
    session.add(ComponentDisposition(component_id=comp.id, disposition=disposition, effective_on=on_date, note=note,
                                     work_session_id=work_session_id, previous_disposition=comp.disposition))
    _apply_disposition(comp, disposition, on_date, note)
    session.flush()
    return comp


def _apply_disposition(comp: Component, disposition: str, on_date: str | None, note: str | None) -> None:
    comp.disposition, comp.disposition_on = disposition, on_date
    if disposition in OUT_OF_USE or disposition == "VOIDED":
        comp.status, comp.retired_on = "RETIRED", on_date
        comp.retire_reason = note or DISPOSITIONS.get(disposition, "record of an undone operation")
    else:  # back in stock (e.g. a repaired tube, or a discard entered by mistake)
        comp.status, comp.retired_on, comp.retire_reason = "ACTIVE", None, None


def refresh_disposition(session: Session, comp: Component) -> None:
    """Current disposition = latest non-voided history row (used after an undo)."""
    last = session.scalar(select(ComponentDisposition).where(
        ComponentDisposition.component_id == comp.id, ComponentDisposition.voided_at.is_(None))
        .order_by(ComponentDisposition.id.desc()).limit(1))
    if last:
        _apply_disposition(comp, last.disposition, last.effective_on, last.note)
    else:
        _apply_disposition(comp, "STORED", None, None)
    session.flush()


def disposition_history(session: Session, comp: Component) -> list[dict]:
    return [{"id": d.id, "disposition": d.disposition, "label": DISPOSITIONS.get(d.disposition, d.disposition),
             "effective_on": d.effective_on, "note": d.note, "work_session_id": d.work_session_id,
             "previous": d.previous_disposition, "voided": bool(d.voided_at)}
            for d in session.scalars(select(ComponentDisposition).where(
                ComponentDisposition.component_id == comp.id).order_by(ComponentDisposition.id))]


def retire_component(session: Session, component_id: int, *, on: str, reason: str | None = None,
                     disposition: str = "RETIRED", work_session_id: int | None = None) -> Component:
    if disposition not in OUT_OF_USE:
        raise DomainError(f"Retiring means one of {', '.join(OUT_OF_USE)}")
    return set_disposition(session, component_id, disposition, on=on, note=reason, work_session_id=work_session_id)


def delete_component(session: Session, component_id: int) -> None:
    comp = get_component(session, component_id)
    has_history = session.scalar(select(func.count()).select_from(Installation).where(
        Installation.component_id == component_id)) or session.scalar(select(func.count()).select_from(
        UsageContribution).where(UsageContribution.component_id == component_id))
    from bikelog.models import MaintenanceEvent
    has_history = has_history or session.scalar(select(func.count()).select_from(MaintenanceEvent).where(
        MaintenanceEvent.component_id == component_id))
    if has_history:
        raise Protected("This component has history. Retire it instead of deleting it.")
    session.query(UsageAdjustment).filter(UsageAdjustment.component_id == component_id).delete()
    session.delete(comp)
    session.flush()


# ---------------------------------------------------------------- installations

def open_installation(session: Session, component_id: int) -> Installation | None:
    return session.scalar(select(Installation).where(
        Installation.component_id == component_id, Installation.removed_utc.is_(None),
        Installation.voided_at.is_(None)))


def _overlaps(a_start: str, a_end: str | None, b_start: str, b_end: str | None) -> bool:
    return a_start < (b_end or FAR_FUTURE) and b_start < (a_end or FAR_FUTURE)


def _validate_slot(comp: Component, slot: str | None, bike_id: int | None, parent: Component | None) -> str:
    ctype = COMPONENT_TYPES[comp.component_type]
    if parent is not None:
        if parent.component_type not in ctype.parent_types:
            raise DomainError(f"A {ctype.name.lower()} cannot be mounted on a "
                              f"{COMPONENT_TYPES[parent.component_type].name.lower()}")
    if slot is None:
        if not ctype.slots:
            raise DomainError("Choose a slot name for this part")
        if len(ctype.slots) > 1 and parent is None:
            raise DomainError(f"Choose a slot: {', '.join(ctype.slots)}")
        slot = ctype.slots[0]
    elif ctype.slots and slot not in ctype.slots:
        raise DomainError(f"A {ctype.name.lower()} goes in slot {', '.join(ctype.slots)}, not {slot}")
    return slot


def check_conflicts(session: Session, *, component_id: int, bike_id: int | None, parent_id: int | None, slot: str,
                    start: str, end: str | None, ignore_id: int | None = None) -> None:
    rows = session.scalars(select(Installation).where(Installation.voided_at.is_(None), or_(
        Installation.component_id == component_id,
        (Installation.slot == slot) & ((Installation.bike_id == bike_id) if bike_id is not None
                                       else (Installation.parent_component_id == parent_id)),
    )))
    for i in rows:
        if i.id == ignore_id or not _overlaps(start, end, i.installed_utc, i.removed_utc):
            continue
        other = session.get(Component, i.component_id)
        where = session.get(Bike, i.bike_id).name if i.bike_id else session.get(Component, i.parent_component_id).label
        period = f"{i.installed_at[:10]} → {i.removed_at[:10] if i.removed_at else 'now'}"
        if i.component_id == component_id:
            raise Conflict(f"{other.label} is already installed on {where} ({i.slot}, {period}) in that period. "
                           "Remove it there first, or move it with an effective date.",
                           installation_id=i.id)
        raise Conflict(f"Slot {slot} on {where} is occupied by {other.label} ({period}). "
                       "Use replace, or remove that part first.", installation_id=i.id)


def install(session: Session, component_id: int, *, at: str, bike_id: int | None = None,
            parent_component_id: int | None = None, slot: str | None = None, until: str | None = None,
            note: str | None = None, reallocate: bool = True, work_session_id: int | None = None) -> Installation:
    comp = get_component(session, component_id)
    if comp.status == "RETIRED":
        word = DISPOSITIONS.get(comp.disposition, "Retired").split(" ")[0].lower()
        raise DomainError(f"{comp.label} is {word if comp.disposition in OUT_OF_USE else 'retired'} and cannot be "
                          "installed. If that was a mistake, put it back in stock first.")
    if comp.disposition == "AWAITING_SERVICE" and until is None:
        raise DomainError(f"{comp.label} is awaiting inspection or repair. Log the repair (or mark it as a usable "
                          "spare) before installing it.")
    if (bike_id is None) == (parent_component_id is None):
        raise DomainError("Install on exactly one bike or one parent component")
    parent = None
    if bike_id is not None:
        bike = get_bike(session, bike_id)
        if bike.status == "RETIRED":
            raise DomainError(f"{bike.name} is retired")
    else:
        parent = get_component(session, parent_component_id)
        if parent.id == comp.id:
            raise DomainError("A part cannot be mounted on itself")
    slot = _validate_slot(comp, slot, bike_id, parent)
    tz = settings.tz(session)
    w = parse_when(at, tz)
    wu = parse_when(until, tz) if until else None
    if wu and wu.utc <= w.utc:
        raise DomainError("Removal must be after installation")
    check_conflicts(session, component_id=comp.id, bike_id=bike_id, parent_id=parent_component_id, slot=slot,
                    start=w.utc, end=wu.utc if wu else None)
    inst = Installation(component_id=comp.id, bike_id=bike_id, parent_component_id=parent_component_id, slot=slot,
                        installed_at=w.raw, installed_utc=w.utc, removed_at=wu.raw if wu else None,
                        removed_utc=wu.utc if wu else None, note=note, install_session_id=work_session_id)
    session.add(inst)
    try:
        session.flush()
    except IntegrityError as e:  # DB-level guard (partial unique index / overlap trigger)
        raise Conflict(f"Conflicting installation: {e.orig}") from e
    if reallocate:
        _reallocate(session)
    return inst


def remove(session: Session, component_id: int, *, at: str, reason: str | None = None,
           outcome: str | None = None, reallocate: bool = True, work_session_id: int | None = None) -> Installation:
    """Take a part off. ``outcome`` answers "what happened to the old item?" (default: stored spare).
    MOVED is used internally when the part goes straight to another position."""
    comp = get_component(session, component_id)
    inst = open_installation(session, component_id)
    if not inst:
        raise DomainError(f"{comp.label} is not installed")
    w = parse_when(at, settings.tz(session))
    if w.utc <= inst.installed_utc:
        raise DomainError(f"{comp.label} was installed on {inst.installed_at[:10]}; removal must be later. "
                          "If the installation itself was wrong, correct (void) it instead.")
    outcome = outcome or "STORED"
    if outcome != "MOVED" and outcome not in DISPOSITIONS:
        raise DomainError(f"What happened to {comp.label}? Choose one of: {', '.join(DISPOSITIONS)}")
    inst.removed_at, inst.removed_utc, inst.removal_reason = w.raw, w.utc, reason
    inst.removal_outcome, inst.removal_session_id = outcome, work_session_id
    session.flush()
    if outcome != "MOVED":
        set_disposition(session, comp.id, outcome, on=at, note=reason, work_session_id=work_session_id)
    if reallocate:
        _reallocate(session)
    return inst


def replace(session: Session, old_component_id: int, *, at: str, new_component_id: int | None = None,
            same_product: bool = False, new: dict | None = None, new_label: str | None = None,
            reason: str | None = None, old_outcome: str | None = None, from_stock_id: int | None = None,
            work_session_id: int | None = None) -> dict:
    """Replace an installed part in the same position.

    The new part is an existing spare (``new_component_id``), a new physical instance of the same
    product (``same_product``), one unit taken from counted stock (``from_stock_id``: the stock goes
    down by one and the unit gets its own identity), or a new item described by ``new`` (label, product_id, price_cents,
    purchase_date, prior_usage). ``old_outcome`` records what happened to the removed part; it keeps
    its identity, mileage and history whatever the outcome.
    """
    old = get_component(session, old_component_id)
    inst = open_installation(session, old_component_id)
    if not inst:
        raise DomainError(f"{old.label} is not installed, nothing to replace")
    ctype = COMPONENT_TYPES[old.component_type]
    outcome = old_outcome or ctype.removed_default
    if new_component_id is not None:
        new_comp = get_component(session, new_component_id)
        if new_comp.id == old.id:
            raise DomainError("Pick a different part; to service the same item, log maintenance on it instead")
        if new_comp.component_type != old.component_type:
            raise DomainError(f"{new_comp.label} is a {new_comp.component_type}, not a {old.component_type}")
        other = open_installation(session, new_comp.id)
        if other:
            raise DomainError(f"{new_comp.label} is installed elsewhere ({location(session, new_comp)['text']}). "
                              "Use 'move' to change its position.")
    elif from_stock_id is not None:
        from bikelog.services import stock
        line = stock.get(session, from_stock_id)
        if line.component_type != old.component_type:
            raise DomainError(f"{line.name} is not stock of {ctype.name.lower()}s")
        new_comp = stock.draw_component(session, line.id, on=at, label=new_label, work_session_id=work_session_id)
    elif same_product or new is not None:
        spec = dict(new or {})
        product_id = spec.pop("product_id", None)
        if same_product:
            product_id = old.product_id
        label = (spec.pop("label", None) or new_label or "").strip() or _next_label(session, old)
        new_comp = create_component(session, component_type=old.component_type, label=label, product_id=product_id,
                                    prior_usage=spec.pop("prior_usage", None) or "NEW",
                                    price_cents=spec.pop("price_cents", None),
                                    purchase_date=spec.pop("purchase_date", None) or at[:10],
                                    notes=spec.pop("notes", None), work_session_id=work_session_id)
        if spec:
            raise DomainError(f"Unknown fields for the new item: {', '.join(spec)}")
    else:
        raise DomainError("Pick a spare, 'replace with the same product', or describe the new item")
    remove(session, old.id, at=at, reason=reason or "replaced", outcome=outcome, reallocate=False,
           work_session_id=work_session_id)
    new_inst = install(session, new_comp.id, at=at, bike_id=inst.bike_id, parent_component_id=inst.parent_component_id,
                       slot=inst.slot, reallocate=False, work_session_id=work_session_id)
    _reallocate(session)
    return {"removed_installation_id": inst.id, "installation_id": new_inst.id, "new_component_id": new_comp.id,
            "new_label": new_comp.label, "old_outcome": outcome}


def move(session: Session, component_id: int, *, at: str, bike_id: int | None = None,
         parent_component_id: int | None = None, slot: str | None = None, swap: bool = False,
         reason: str | None = None, work_session_id: int | None = None) -> dict:
    """Position change (e.g. tire from rear wheel to front): same identity, mileage carries on.
    With ``swap`` the part occupying the target goes to this part's old position at the same moment."""
    comp = get_component(session, component_id)
    cur = open_installation(session, component_id)
    target_slot = _validate_slot(comp, slot, bike_id,
                                 get_component(session, parent_component_id) if parent_component_id else None)
    if cur and cur.bike_id == bike_id and cur.parent_component_id == parent_component_id and cur.slot == target_slot:
        raise DomainError(f"{comp.label} is already in that position")
    occupant = session.scalar(select(Installation).where(
        Installation.voided_at.is_(None), Installation.removed_utc.is_(None), Installation.slot == target_slot,
        (Installation.bike_id == bike_id) if bike_id is not None
        else (Installation.parent_component_id == parent_component_id)))
    if occupant and not swap:
        other = get_component(session, occupant.component_id)
        raise Conflict(f"That position is occupied by {other.label}. Swap them, or replace/remove it first.")
    if occupant and not cur:
        raise DomainError("Swapping needs both parts installed")
    where = (get_bike(session, bike_id).name if bike_id else get_component(session, parent_component_id).label)
    note = reason or f"moved to {where} ({target_slot.replace('_', ' ').lower()})"
    if cur:
        remove(session, comp.id, at=at, reason=note, outcome="MOVED", reallocate=False, work_session_id=work_session_id)
    moved_back = None
    if occupant:
        remove(session, occupant.component_id, at=at, reason=f"swapped with {comp.label}", outcome="MOVED",
               reallocate=False, work_session_id=work_session_id)
        moved_back = install(session, occupant.component_id, at=at, bike_id=cur.bike_id,
                             parent_component_id=cur.parent_component_id, slot=cur.slot, reallocate=False,
                             work_session_id=work_session_id).id
    new_inst = install(session, comp.id, at=at, bike_id=bike_id, parent_component_id=parent_component_id,
                       slot=target_slot, reallocate=False, work_session_id=work_session_id)
    _reallocate(session)
    return {"installation_id": new_inst.id, "swapped_installation_id": moved_back}


def spare_stock(session: Session) -> list[dict]:
    """Individual items that are off the bike and still in use, grouped by type and product.
    Installing a spare takes it out of this count; discarding the removed part never touches it."""
    groups: dict[tuple, dict] = {}
    for c in session.scalars(select(Component).where(Component.status == "ACTIVE").order_by(Component.label)):
        if open_installation(session, c.id):
            continue
        key = (c.component_type, c.product_id)
        g = groups.setdefault(key, {
            "component_type": c.component_type, "type_name": COMPONENT_TYPES[c.component_type].name,
            "product_id": c.product_id,
            "product": f"{c.product.maker or ''} {c.product.model}".strip() if c.product else None,
            "ready": 0, "awaiting_service": 0, "items": []})
        g["ready" if c.disposition == "STORED" else "awaiting_service"] += 1
        g["items"].append({"id": c.id, "label": c.label, "disposition": c.disposition})
    return sorted(groups.values(), key=lambda g: (g["type_name"], g["product"] or ""))


def _next_label(session: Session, old: Component) -> str:
    base = old.label
    n = 2
    while session.scalar(select(Component).where(Component.component_type == old.component_type,
                                                 func.lower(Component.label) == f"{base} ({n})".lower())):
        n += 1
    return f"{base} ({n})"


def void_installation(session: Session, installation_id: int, reason: str) -> Installation:
    """Correction: the installation record was wrong. It stays in history, marked void."""
    inst = session.get(Installation, installation_id)
    if not inst:
        raise NotFound("Installation not found")
    if not reason:
        raise DomainError("Say why this installation record is wrong")
    inst.voided_at, inst.void_reason = utc_now(), reason
    session.flush()
    _reallocate(session)
    return inst


def correct_installation(session: Session, installation_id: int, *, installed_at: str | None = None,
                         removed_at: str | None = None, clear_removed: bool = False, reason: str) -> Installation:
    """Correction of dates (not a replacement). Use with dry_run first to preview mileage impact."""
    inst = session.get(Installation, installation_id)
    if not inst or inst.voided_at:
        raise NotFound("Installation not found")
    if not reason:
        raise DomainError("Say why the dates are corrected")
    tz = settings.tz(session)
    start = parse_when(installed_at, tz) if installed_at else None
    end = parse_when(removed_at, tz) if removed_at else None
    new_start = start.utc if start else inst.installed_utc
    new_end = None if clear_removed else (end.utc if end else inst.removed_utc)
    if new_end and new_end <= new_start:
        raise DomainError("Removal must be after installation")
    check_conflicts(session, component_id=inst.component_id, bike_id=inst.bike_id, parent_id=inst.parent_component_id,
                    slot=inst.slot, start=new_start, end=new_end, ignore_id=inst.id)
    if start:
        inst.installed_at, inst.installed_utc = start.raw, start.utc
    if clear_removed:
        inst.removed_at = inst.removed_utc = None
    elif end:
        inst.removed_at, inst.removed_utc = end.raw, end.utc
    inst.note = ((inst.note + "\n") if inst.note else "") + f"Corrected: {reason}"
    session.flush()
    _reallocate(session)
    return inst


# ---------------------------------------------------------------- views

def location(session: Session, comp: Component) -> dict:
    if comp.status == "RETIRED":
        word = {"DISCARDED": "Discarded", "SOLD": "Sold / given away",
                "VOIDED": "Record of an undone operation"}.get(comp.disposition, "Retired")
        return {"state": "RETIRED", "disposition": comp.disposition,
                "text": f"{word} {comp.retired_on or ''}".strip()}
    inst = open_installation(session, comp.id)
    if not inst:
        if comp.disposition == "AWAITING_SERVICE":
            return {"state": "AWAITING_SERVICE", "disposition": comp.disposition,
                    "text": "Awaiting inspection or repair"}
        return {"state": "STORED", "disposition": comp.disposition, "text": "In storage (spare)"}
    path = []
    cur = inst
    while cur is not None and cur.parent_component_id is not None:
        parent = session.get(Component, cur.parent_component_id)
        path.append(parent.label)
        cur = open_installation(session, parent.id)
    bike = session.get(Bike, cur.bike_id) if cur is not None and cur.bike_id else None
    text = (bike.name if bike else "unmounted parent") + (" → " + " → ".join(reversed(path)) if path else "")
    return {"state": "INSTALLED", "bike_id": bike.id if bike else None, "bike": bike.name if bike else None,
            "slot": inst.slot, "parent_component_id": inst.parent_component_id, "since": inst.installed_at,
            "installation_id": inst.id, "text": f"{text} ({inst.slot.replace('_', ' ').lower()})"}


def installation_history(session: Session, comp: Component) -> list[dict]:
    out = []
    for i in session.scalars(select(Installation).where(Installation.component_id == comp.id)
                             .order_by(Installation.installed_utc)):
        km = session.scalar(select(func.sum(UsageContribution.km)).where(
            UsageContribution.component_id == comp.id, UsageContribution.state == "COUNTED",
            UsageContribution.sort_utc >= i.installed_utc,
            UsageContribution.sort_utc < (i.removed_utc or FAR_FUTURE))) if not i.voided_at else None
        where = session.get(Bike, i.bike_id).name if i.bike_id else session.get(Component, i.parent_component_id).label
        out.append({"id": i.id, "where": where, "bike_id": i.bike_id, "parent_component_id": i.parent_component_id,
                    "slot": i.slot, "installed_at": i.installed_at, "removed_at": i.removed_at,
                    "removal_reason": i.removal_reason, "removal_outcome": i.removal_outcome,
                    "voided": bool(i.voided_at), "void_reason": i.void_reason,
                    "note": i.note, "km": round(float(km or 0), 3) if km is not None else None})
    return out


def bike_setup(session: Session, bike: Bike) -> list[dict]:
    """Current setup as a tree: bike slots, and parts mounted on parts."""
    def children(component_id: int, depth: int) -> list[dict]:
        rows = []
        for i in session.scalars(select(Installation).where(
                Installation.parent_component_id == component_id, Installation.removed_utc.is_(None),
                Installation.voided_at.is_(None)).order_by(Installation.slot)):
            c = session.get(Component, i.component_id)
            rows.append(_setup_row(c, i, depth))
            rows.extend(children(c.id, depth + 1))
        return rows
    rows = []
    for i in session.scalars(select(Installation).where(
            Installation.bike_id == bike.id, Installation.removed_utc.is_(None),
            Installation.voided_at.is_(None)).order_by(Installation.slot)):
        c = session.get(Component, i.component_id)
        rows.append(_setup_row(c, i, 0))
        rows.extend(children(c.id, 1))
    return rows


def _setup_row(c: Component, i: Installation, depth: int) -> dict:
    return {"component_id": c.id, "label": c.label, "component_type": c.component_type,
            "type_name": COMPONENT_TYPES[c.component_type].name, "slot": i.slot, "since": i.installed_at,
            "installation_id": i.id, "depth": depth, "parent_component_id": i.parent_component_id}


def bike_installation_history(session: Session, bike: Bike) -> list[dict]:
    rows = []
    for i in session.scalars(select(Installation).where(Installation.bike_id == bike.id)
                             .order_by(Installation.installed_utc.desc())):
        c = session.get(Component, i.component_id)
        rows.append({"id": i.id, "component_id": c.id, "label": c.label, "slot": i.slot,
                     "installed_at": i.installed_at, "removed_at": i.removed_at, "removal_reason": i.removal_reason,
                     "removal_outcome": i.removal_outcome, "voided": bool(i.voided_at), "void_reason": i.void_reason})
    return rows
