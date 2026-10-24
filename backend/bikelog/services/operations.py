"""Cross-cutting operation helpers: mileage-change preview (dry run) and client_op_id idempotency."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.models import Component, Operation
from bikelog.services.usage import component_totals


class _Rollback(Exception):
    pass


def _deltas(session: Session, before: dict[int, float], after: dict[int, float]) -> list[dict]:
    ids = sorted(k for k in set(before) | set(after) if abs(before.get(k, 0.0) - after.get(k, 0.0)) > 1e-9)
    names = dict(session.execute(select(Component.id, Component.label).where(Component.id.in_(ids))).all()) if ids else {}
    out = []
    for cid in ids:
        b, a = before.get(cid, 0.0), after.get(cid, 0.0)
        out.append({"component_id": cid, "label": names.get(cid, f"#{cid}"), "before_km": round(b, 3),
                    "after_km": round(a, 3), "delta_km": round(a - b, 3)})
    return out


def notice(deltas: list[dict], preview: bool) -> str:
    prefix = "Preview: " if preview else ""
    if not deltas:
        return prefix + "No component mileage changes."
    parts = [f"{d['label']} {'+' if d['delta_km'] > 0 else '−'}{abs(d['delta_km']):,.1f} km" for d in deltas]
    return prefix + "; ".join(parts) + "."


def with_change(session: Session, fn: Callable[[], Any], *, dry_run: bool = False) -> tuple[Any, dict]:
    """Run fn inside a savepoint and report per-component km deltas. dry_run rolls everything back."""
    before = component_totals(session)
    result: Any = None
    change: dict = {}
    try:
        with session.begin_nested():
            result = fn()
            session.flush()
            after = component_totals(session)
            deltas = _deltas(session, before, after)
            change = {"preview": dry_run, "deltas": deltas, "notice": notice(deltas, dry_run)}
            if dry_run:
                raise _Rollback()
    except _Rollback:
        session.expire_all()
    return result, change


def run_once(session: Session, client_op_id: str | None, kind: str, fn: Callable[[], dict]) -> dict:
    """Execute fn once per client_op_id. A repeat (double click, retry after timeout) returns the first result."""
    if not client_op_id:
        return fn()
    existing = session.scalar(select(Operation).where(Operation.client_op_id == client_op_id))
    if existing:
        result = json.loads(existing.result_json)
        result["repeated"] = True
        return result
    result = fn()
    if not (isinstance(result.get("change"), dict) and result["change"].get("preview")):
        session.add(Operation(client_op_id=client_op_id, kind=kind, result_json=json.dumps(result, default=str)))
        session.flush()
    return result
