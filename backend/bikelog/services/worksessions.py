"""Work sessions: one visit to the bench, grouping the separate transactions it produced.

A replacement is several transactions: maybe a purchase (new item) or a stock use (spare from stock),
the removal with the old item's outcome, the installation, and any supplies or service events.
They stay separate records (so stock and money are each counted once) and point to their session,
which lets the session be summarised and undone as a whole.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS, DISPOSITIONS
from bikelog.models import (
    Component, ComponentDisposition, ConsumableTxn, Installation, MaintenanceEvent, WorkSession,
)
from bikelog.services import allocation, settings
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import check_conflicts, refresh_disposition
from bikelog.timeutil import parse_when, utc_now


def begin(session: Session, *, at: str, bike_id: int | None = None, title: str | None = None,
          notes: str | None = None) -> WorkSession:
    w = parse_when(at, settings.tz(session))
    ws = WorkSession(performed_at=w.raw, performed_on=w.local_date, bike_id=bike_id, title=title, notes=notes)
    session.add(ws)
    session.flush()
    return ws


def get(session: Session, ws_id: int) -> WorkSession:
    ws = session.get(WorkSession, ws_id)
    if not ws:
        raise NotFound("Work session not found")
    return ws


def _label(session: Session, cid: int | None) -> str | None:
    c = session.get(Component, cid) if cid else None
    return c.label if c else None


def summary(session: Session, ws_id: int) -> dict:
    ws = get(session, ws_id)
    rows: list[dict] = []
    cost = 0
    for c in session.scalars(select(Component).where(Component.purchase_session_id == ws.id)):
        if c.from_stock_txn_id:
            continue  # its USE row below; the cost belongs to the earlier stock purchase
        rows.append({"kind": "NEW_ITEM", "text": f"New item {c.label}", "component_id": c.id,
                     "cost_cents": c.price_cents})
        cost += c.price_cents or 0
    for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.work_session_id == ws.id)):
        from bikelog.models import Consumable
        line = session.get(Consumable, t.consumable_id)
        text = {"PURCHASE": "Bought", "RETURN": "Returned to shop", "ADJUST": "Stock corrected",
                "USE": "Used from stock"}[t.kind]
        if t.kind == "ADJUST" and (t.note or "").lower() == "starting stock":
            text = "Starting stock"
        qty = "" if t.qty is None else f"{t.qty:g} {line.unit} "
        extra = f" → {_label(session, t.component_id)}" if t.component_id else ""
        rows.append({"kind": f"STOCK_{t.kind}", "text": f"{text}: {qty}{line.name}{extra}", "txn_id": t.id,
                     "cost_cents": t.cost_cents, "voided": bool(t.voided_at)})
        if not t.voided_at and t.cost_cents:
            cost += t.cost_cents * (1 if t.kind == "PURCHASE" else -1)
    for i in session.scalars(select(Installation).where(Installation.removal_session_id == ws.id)):
        out = "moved" if i.removal_outcome == "MOVED" else DISPOSITIONS.get(i.removal_outcome or "", "")
        rows.append({"kind": "REMOVE", "text": f"Removed {_label(session, i.component_id)} ({i.slot.replace('_', ' ').lower()}): {out.lower()}",
                     "installation_id": i.id, "reason": i.removal_reason})
    for i in session.scalars(select(Installation).where(Installation.install_session_id == ws.id)):
        rows.append({"kind": "INSTALL", "text": f"Installed {_label(session, i.component_id)} ({i.slot.replace('_', ' ').lower()})",
                     "installation_id": i.id, "voided": bool(i.voided_at)})
    for d in session.scalars(select(ComponentDisposition).where(ComponentDisposition.work_session_id == ws.id)):
        rows.append({"kind": "DISPOSITION", "text": f"{_label(session, d.component_id)}: "
                     f"{DISPOSITIONS.get(d.disposition, d.disposition)}", "voided": bool(d.voided_at)})
    for e in session.scalars(select(MaintenanceEvent).where(MaintenanceEvent.work_session_id == ws.id)):
        a = ACTIONS.get(e.action_code)
        rows.append({"kind": "EVENT", "text": f"{a.name if a else e.action_code}: {_label(session, e.component_id)}",
                     "event_id": e.id, "cost_cents": e.cost_cents, "voided": bool(e.voided_at)})
        if not e.voided_at:
            cost += e.cost_cents or 0
    from bikelog.models import JournalEntry
    for j in session.scalars(select(JournalEntry).where(JournalEntry.repair_session_id == ws.id)):
        rows.append({"kind": "INCIDENT_FIX", "text": f"Incident fixed: {_label(session, j.component_id) or j.affected}: "
                     f"{j.repair_text}"})
    return {"id": ws.id, "uuid": ws.uuid, "performed_at": ws.performed_at, "bike_id": ws.bike_id,
            "title": ws.title, "notes": ws.notes, "undone_at": ws.undone_at, "undo_reason": ws.undo_reason,
            "transactions": rows, "cost_cents": cost}


def recent(session: Session, limit: int = 50) -> list[dict]:
    return [summary(session, ws.id) for ws in session.scalars(
        select(WorkSession).order_by(WorkSession.id.desc()).limit(limit))]


def undo(session: Session, ws_id: int, reason: str | None = None) -> dict:
    """Reverse a whole session consistently: installs voided, removals reopened, dispositions and
    stock transactions voided (stock comes back), events voided, items it created marked VOIDED.
    Nothing is deleted. Refused when later records depend on it."""
    ws = get(session, ws_id)
    if ws.undone_at:
        raise DomainError("This session was already undone")
    now = utc_now()
    reason = reason or "undone"
    created = list(session.scalars(select(Component).where(Component.purchase_session_id == ws.id)))
    created_ids = {c.id for c in created}
    new_insts = list(session.scalars(select(Installation).where(Installation.install_session_id == ws.id,
                                                                Installation.voided_at.is_(None))))
    removals = list(session.scalars(select(Installation).where(Installation.removal_session_id == ws.id,
                                                               Installation.voided_at.is_(None))))
    for i in new_insts:
        if i.removed_utc and i.removal_session_id != ws.id:
            raise DomainError(f"{_label(session, i.component_id)} was changed again later; undo that first")
    for cid in created_ids:
        later = session.scalar(select(Installation.id).where(
            Installation.component_id == cid, Installation.voided_at.is_(None),
            (Installation.install_session_id.is_(None)) | (Installation.install_session_id != ws.id)))
        later_ev = session.scalar(select(MaintenanceEvent.id).where(
            MaintenanceEvent.component_id == cid, MaintenanceEvent.voided_at.is_(None),
            (MaintenanceEvent.work_session_id.is_(None)) | (MaintenanceEvent.work_session_id != ws.id)))
        if later or later_ev:
            raise DomainError(f"{_label(session, cid)} has later history; undo or correct that first")
    for i in new_insts:
        i.voided_at, i.void_reason = now, f"undone: {reason}"
    session.flush()
    for i in removals:
        check_conflicts(session, component_id=i.component_id, bike_id=i.bike_id, parent_id=i.parent_component_id,
                        slot=i.slot, start=i.installed_utc, end=None, ignore_id=i.id)
        i.removed_at = i.removed_utc = None
        i.removal_undone_at = now
        i.note = ((i.note + "\n") if i.note else "") + f"Removal undone: {reason}"
    session.flush()
    touched = set()
    for d in session.scalars(select(ComponentDisposition).where(ComponentDisposition.work_session_id == ws.id,
                                                                ComponentDisposition.voided_at.is_(None))):
        d.voided_at = now
        touched.add(d.component_id)
    for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.work_session_id == ws.id,
                                                         ConsumableTxn.voided_at.is_(None))):
        t.voided_at = now
    for e in session.scalars(select(MaintenanceEvent).where(MaintenanceEvent.work_session_id == ws.id,
                                                            MaintenanceEvent.voided_at.is_(None))):
        e.voided_at, e.void_reason = now, f"undone: {reason}"
    session.flush()
    for cid in touched - created_ids:
        refresh_disposition(session, session.get(Component, cid))
    for c in created:
        session.add(ComponentDisposition(component_id=c.id, disposition="VOIDED", previous_disposition=c.disposition,
                                         effective_on=ws.performed_on, note=f"created by undone session {ws.id}"))
        c.disposition, c.status, c.retired_on = "VOIDED", "RETIRED", ws.performed_on
        c.retire_reason = "record of an undone operation"
    from bikelog.models import PurchaseBundle
    for b in session.scalars(select(PurchaseBundle).where(PurchaseBundle.work_session_id == ws.id,
                                                          PurchaseBundle.voided_at.is_(None))):
        b.voided_at, b.void_reason = now, f"undone: {reason}"
    from bikelog.services import repairs
    repairs.clear_for_session(session, ws.id)          # an incident fixed in this session is open again
    ws.undone_at, ws.undo_reason = now, reason
    session.flush()
    allocation.rebuild_all(session, settings.tz(session))
    return summary(session, ws.id)
