"""Broken spokes, logged on the wheel (DECISIONS 109).

A broken spoke is a "Broken spoke" incident on the wheel: the day it broke, and (now or later) the day it was
replaced, with a spoke from stock or not. Replacing goes through the incident's fix (repairs.fix), so the
"Replace broken spoke" event, the stock use and Undo work as for any incident. The count since the wheel was
laced, and the "replace the wheel" reminder at the limit (Settings, default 3), come from
maintenance.spoke_info. Removing a wrong entry undoes its replacement and voids it (restorable).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from bikelog.catalog import WHEEL_TYPES
from bikelog.models import new_uuid
from bikelog.services import incidents, journal, repairs
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services.errors import DomainError


def _wheel(session: Session, wheel_id: int):
    wheel = inv.get_component(session, wheel_id)
    if wheel.component_type not in WHEEL_TYPES:
        raise DomainError("A broken spoke is logged on a front or rear wheel")
    return wheel


def _source(stock_line_id: int | None) -> dict:
    return {"kind": "stock", "id": stock_line_id} if stock_line_id else {"kind": "untracked"}


def log_broken(session: Session, wheel_id: int, *, broke_on: str, replaced_on: str | None = None,
               stock_line_id: int | None = None, note: str | None = None) -> dict:
    """A spoke broke on ``broke_on``; with ``replaced_on`` it was also replaced (a spoke from stock or not)."""
    wheel = _wheel(session, wheel_id)
    if not broke_on:
        raise DomainError("Give the day the spoke broke")
    if replaced_on and replaced_on[:10] < broke_on[:10]:
        raise DomainError("The spoke cannot be replaced before it broke")
    group = new_uuid()
    e = journal.add(session, text=(note or "").strip() or None, on=broke_on[:10], component_id=wheel.id,
                    incident_type="SPOKE", incident_group=group)
    if replaced_on:
        repairs.fix(session, group, at=replaced_on,
                    parts=[{"entry_id": e.id, "action": "REPLACED", "source": _source(stock_line_id)}])
    session.flush()
    return {"group": group, "spokes": m.spoke_info(session, wheel)}


def mark_replaced(session: Session, wheel_id: int, group: str, *, replaced_on: str,
                  stock_line_id: int | None = None) -> dict:
    wheel = _wheel(session, wheel_id)
    e = next((b for b in m.spoke_breaks(session, wheel) if b["group"] == group), None)
    if e is None:
        raise DomainError("That broken spoke is not on this wheel")
    if e["repair"]:
        raise DomainError("That spoke is already marked as replaced")
    if not replaced_on or replaced_on[:10] < e["broke_on"]:
        raise DomainError("Give the day it was replaced (not before it broke)")
    repairs.fix(session, group, at=replaced_on,
                parts=[{"entry_id": e["entry_id"], "action": "REPLACED", "source": _source(stock_line_id)}])
    session.flush()
    return m.spoke_info(session, wheel)


def remove_broken(session: Session, wheel_id: int, group: str) -> dict:
    """A wrong entry: its replacement is undone (a stock spoke comes back) and it is voided (restorable)."""
    wheel = _wheel(session, wheel_id)
    e = next((b for b in m.spoke_breaks(session, wheel) if b["group"] == group), None)
    if e is None:
        raise DomainError("That broken spoke is not on this wheel")
    if e["repair"]:
        repairs.undo_fix(session, group)
    incidents.remove(session, group)
    session.flush()
    return m.spoke_info(session, wheel)
