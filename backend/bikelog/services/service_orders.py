"""Send a part away for service or repair, and record what came back (DECISIONS 97).

Any part can go: a frame to the maker, a wheel to the wheel builder, a Di2 derailleur to the shop.
Sending takes it off the bike (it collects no km while away; parts mounted on it go along) and marks it
"awaiting repair". The return is one of four outcomes:

* REPAIRED_PAID      repaired, you paid (the cost is a REPAIR event: bike costs and the part's history)
* REPAIRED_WARRANTY  repaired under warranty (a cost such as shipping can still be entered)
* REPLACED_WARRANTY  replaced under warranty: the old part is "returned under warranty" and keeps its km,
                     a new part (0 km, own serial and warranty date) takes its place
* NOT_REPAIRED       came back unrepaired (kept as a stored part, or discarded)

The repaired or new part can go straight back where the old one was; a part fitted meanwhile (a spare
wheel) is stored. A linked incident gets the fix recorded and is solved when nothing else is open.
Both steps are work sessions, so Undo works as everywhere (clear_for_session)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES
from bikelog.models import Bike, Component, Installation, JournalEntry, ServiceOrder
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import settings, worksessions
from bikelog.services.errors import DomainError, NotFound
from bikelog.timeutil import parse_when

OUTCOMES = {"REPAIRED_PAID": "Repaired (paid)", "REPAIRED_WARRANTY": "Repaired under warranty",
            "REPLACED_WARRANTY": "Replaced under warranty", "NOT_REPAIRED": "Not repaired"}


def get(session: Session, order_id: int) -> ServiceOrder:
    o = session.get(ServiceOrder, order_id)
    if o is None:
        raise NotFound("Service order not found")
    return o


def open_order(session: Session, component_id: int) -> ServiceOrder | None:
    return session.scalar(select(ServiceOrder).where(ServiceOrder.component_id == component_id,
                                                     ServiceOrder.status == "OUT"))


def _incident_entries(session: Session, group: str) -> list[JournalEntry]:
    return list(session.scalars(select(JournalEntry).where(JournalEntry.incident_group == group,
                                                           JournalEntry.voided_at.is_(None))))


def send_out(session: Session, component_id: int, *, at: str, shop: str | None = None, reason: str | None = None,
             incident_group: str | None = None) -> dict:
    comp = inv.get_component(session, component_id)
    if comp.status == "RETIRED":
        raise DomainError(f"{comp.label} is out of use; put it back in stock first")
    if open_order(session, comp.id):
        raise DomainError(f"{comp.label} is already away for repair")
    if incident_group and not _incident_entries(session, incident_group):
        raise DomainError("That incident does not exist")
    loc = inv.location(session, comp)
    inst = inv.open_installation(session, comp.id)
    shop = (shop or "").strip() or None
    reason = (reason or "").strip() or None
    w = parse_when(at, settings.tz(session))
    title = f"Sent away for repair: {comp.label}" + (f" ({shop})" if shop else "")
    ws = worksessions.begin(session, at=at, bike_id=loc.get("bike_id"), title=title, notes=reason)
    note = "sent away for repair" + (f" to {shop}" if shop else "")
    if inst is not None:
        inv.remove(session, comp.id, at=at, reason=note, outcome="AWAITING_SERVICE", work_session_id=ws.id)
    else:
        inv.set_disposition(session, comp.id, "AWAITING_SERVICE", on=at, note=note, work_session_id=ws.id)
    o = ServiceOrder(component_id=comp.id, bike_id=loc.get("bike_id"),
                     from_bike_id=inst.bike_id if inst else None, from_parent_id=inst.parent_component_id if inst else None,
                     from_slot=inst.slot if inst else None, sent_at=w.raw, sent_on=w.local_date, shop=shop,
                     reason=reason, incident_group=incident_group, send_session_id=ws.id, status="OUT")
    session.add(o)
    session.flush()
    return {"order_id": o.id, "work_session_id": ws.id}


def _put_back(session: Session, o: ServiceOrder, comp: Component, *, at: str, ws_id: int) -> str | None:
    """Back into the position it was sent from; a part fitted there meanwhile goes to storage."""
    if o.from_slot is None:
        return None
    if o.from_bike_id is not None:
        bike = session.get(Bike, o.from_bike_id)
        if bike is None or bike.status != "ACTIVE":
            raise DomainError(f"{bike.name if bike else 'That bike'} is retired; untick 'put it back'")
    elif inv.open_installation(session, o.from_parent_id) is None and session.get(Component, o.from_parent_id).status != "ACTIVE":
        raise DomainError("The part it was mounted on is out of use; untick 'put it back'")
    occupant = session.scalar(select(Installation).where(
        Installation.voided_at.is_(None), Installation.removed_utc.is_(None), Installation.slot == o.from_slot,
        (Installation.bike_id == o.from_bike_id) if o.from_bike_id is not None
        else (Installation.parent_component_id == o.from_parent_id)))
    if occupant is not None:
        inv.replace(session, occupant.component_id, at=at, new_component_id=comp.id, old_outcome="STORED",
                    reason=f"{comp.label} back from repair", work_session_id=ws_id)
        return f"back on, {inv.get_component(session, occupant.component_id).label} stored"
    inv.install(session, comp.id, at=at, bike_id=o.from_bike_id, parent_component_id=o.from_parent_id,
                slot=o.from_slot, note="back from repair", work_session_id=ws_id)
    return "back on"


def return_part(session: Session, order_id: int, *, at: str, outcome: str, cost_cents: int | None = None,
                receipt_ref: str | None = None, notes: str | None = None, put_back: bool = True,
                keep_as: str = "STORED", new_label: str | None = None, new_serial: str | None = None,
                new_warranty_until: str | None = None) -> dict:
    o = get(session, order_id)
    if o.status != "OUT":
        raise DomainError("This part is not away any more")
    if outcome not in OUTCOMES:
        raise DomainError(f"What came back? Choose one of: {', '.join(OUTCOMES.values())}")
    if cost_cents is not None and cost_cents < 0:
        raise DomainError("The cost cannot be negative")
    w = parse_when(at, settings.tz(session))
    if w.utc <= parse_when(o.sent_at, settings.tz(session)).utc:
        raise DomainError(f"It was sent away on {o.sent_on}; it must come back later")
    comp = inv.get_component(session, o.component_id)
    receipt_ref = (receipt_ref or "").strip() or None
    notes = (notes or "").strip() or None
    ws = worksessions.begin(session, at=at, bike_id=o.bike_id,
                            title=f"Back from repair: {comp.label} ({OUTCOMES[outcome].lower()})", notes=notes)
    details = "; ".join(x for x in (OUTCOMES[outcome], o.shop, f"receipt {receipt_ref}" if receipt_ref else None,
                                     notes) if x)
    back = comp
    replacement = None
    if outcome == "REPLACED_WARRANTY":
        label = (new_label or "").strip() or inv._next_label(session, comp)
        replacement = inv.create_component(session, component_type=comp.component_type, label=label,
                                           product_id=comp.product_id, prior_usage="NEW", purchase_date=w.local_date,
                                           notes=f"Warranty replacement for {comp.label}", work_session_id=ws.id)
        inv.update_component(session, replacement.id, serial_number=(new_serial or "").strip() or None,
                             warranty_until=new_warranty_until)
        back = replacement
        after = "WARRANTY_RETURN"
        work = f"replaced under warranty by {replacement.label}"
    elif outcome == "NOT_REPAIRED":
        if keep_as not in ("STORED", "DISCARDED"):
            raise DomainError("Keep it (stored) or discard it")
        after, work = keep_as, "not repaired"
        put_back = False
    else:
        after, work = "STORED", "repaired" + (" under warranty" if outcome == "REPAIRED_WARRANTY" else "")
    ev = m.log_event(session, action_code="REPAIR", at=at, component_id=comp.id, bike_id=o.bike_id,
                     work_done=work, notes=details, cost_cents=cost_cents or None, work_session_id=ws.id,
                     disposition_after=after, symptom=o.reason)
    placed = _put_back(session, o, back, at=at, ws_id=ws.id) if put_back else None
    o.status, o.returned_at, o.returned_on, o.outcome = "BACK", w.raw, w.local_date, outcome
    o.cost_cents, o.receipt_ref, o.return_notes = cost_cents, receipt_ref, notes
    o.return_session_id, o.event_id = ws.id, ev.id
    o.replacement_id = replacement.id if replacement else None
    solved = _fix_incident(session, o, comp, work, w.local_date, ws.id) if o.incident_group else None
    session.flush()
    return {"work_session_id": ws.id, "replacement_id": o.replacement_id, "placed": placed, "incident_solved": solved}


def _fix_incident(session: Session, o: ServiceOrder, comp: Component, work: str, on: str, ws_id: int) -> bool:
    """Record the repair on the incident entries for this part (or, if it lists none, the whole-bike entry)."""
    rows = _incident_entries(session, o.incident_group)
    mine = [e for e in rows if e.component_id == comp.id and not e.repair]
    if not mine:
        mine = [e for e in rows if e.component_id is None and e.affected is None and not e.repair]
    text = f"{work}" + (f" by {o.shop}" if o.shop else "") + (f", {o.cost_cents / 100:.2f} €" if o.cost_cents else "")
    for e in mine:
        e.repair = "REPLACED" if o.outcome == "REPLACED_WARRANTY" else "REPAIRED"
        e.repair_text, e.repaired_on, e.repair_session_id = text, on, ws_id
    solved = bool(rows) and all(e.repair for e in rows)
    if solved:
        for e in rows:
            e.resolved_on = max(x.repaired_on for x in rows)
    return solved


def clear_for_session(session: Session, ws_id: int) -> None:
    """Called when a work session is undone: an undone send voids the order, an undone return reopens it."""
    for o in session.scalars(select(ServiceOrder).where(ServiceOrder.send_session_id == ws_id)):
        o.status = "VOIDED"
    for o in session.scalars(select(ServiceOrder).where(ServiceOrder.return_session_id == ws_id)):
        o.status, o.returned_at, o.returned_on, o.outcome = "OUT", None, None, None
        o.cost_cents = o.receipt_ref = o.return_notes = None
        o.return_session_id = o.event_id = o.replacement_id = None
    session.flush()


def row(session: Session, o: ServiceOrder) -> dict:
    comp = session.get(Component, o.component_id)
    where = None
    if o.from_bike_id:
        b = session.get(Bike, o.from_bike_id)
        where = b.name if b else None
    elif o.from_parent_id:
        p = session.get(Component, o.from_parent_id)
        where = p.label if p else None
    bike = session.get(Bike, o.bike_id) if o.bike_id else None
    rep = session.get(Component, o.replacement_id) if o.replacement_id else None
    incident = None
    if o.incident_group:
        rows = _incident_entries(session, o.incident_group)
        if rows:
            from bikelog.catalog import INCIDENT_TYPES
            incident = {"group": o.incident_group, "label": INCIDENT_TYPES.get(rows[0].incident_type, rows[0].incident_type),
                        "on": rows[0].entry_on, "ride_id": rows[0].ride_id, "open": not rows[0].resolved_on}
    return {"id": o.id, "component_id": o.component_id, "label": comp.label if comp else None,
            "type_name": COMPONENT_TYPES[comp.component_type].name if comp else None,
            "bike_id": o.bike_id, "bike": bike.name if bike else None,
            "from": where, "from_slot": o.from_slot, "sent_on": o.sent_on, "shop": o.shop, "reason": o.reason,
            "status": o.status, "returned_on": o.returned_on, "outcome": o.outcome,
            "outcome_text": OUTCOMES.get(o.outcome) if o.outcome else None, "cost_cents": o.cost_cents,
            "receipt_ref": o.receipt_ref, "notes": o.return_notes, "event_id": o.event_id,
            "replacement_id": o.replacement_id, "replacement": rep.label if rep else None, "incident": incident}


def for_component(session: Session, comp: Component) -> list[dict]:
    """Every service order of this part, and the one that brought it in (warranty replacement)."""
    q = select(ServiceOrder).where(ServiceOrder.status != "VOIDED",
                                   (ServiceOrder.component_id == comp.id) | (ServiceOrder.replacement_id == comp.id))
    return [row(session, o) for o in session.scalars(q.order_by(ServiceOrder.sent_at.desc(), ServiceOrder.id.desc()))]


def away(session: Session, bike_id: int | None = None) -> list[dict]:
    q = select(ServiceOrder).where(ServiceOrder.status == "OUT")
    if bike_id is not None:
        q = q.where(ServiceOrder.bike_id == bike_id)
    return [row(session, o) for o in session.scalars(q.order_by(ServiceOrder.sent_at))]


def incident_choices(session: Session, comp: Component) -> list[dict]:
    """Open incidents to link when sending this part away: the part's own and its bike's."""
    from bikelog.services import incidents
    loc = inv.location(session, comp)
    rows = incidents.all_incidents(session, component_id=comp.id, open_only=True)
    if loc.get("bike_id"):
        rows += incidents.all_incidents(session, bike_id=loc["bike_id"], open_only=True)
    seen, out = set(), []
    for r in rows:
        if r["group"] not in seen:
            seen.add(r["group"])
            out.append({"group": r["group"], "label": r["label"], "on": r["on"], "bike": r["bike"],
                        "affected": ", ".join(a["label"] for a in r["affected"])})
    return out
