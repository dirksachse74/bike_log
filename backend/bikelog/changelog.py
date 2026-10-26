"""Change log of bikes and parts, written automatically on every flush.

Every created bike/part, every changed field (old -> new, as readable text) and every installation event
(installed, removed, corrected, voided) becomes a ``change_log`` row with the time and who made it.
Nothing has to call this: an ``after_flush`` hook on all sessions finds the changes, so new code paths are
covered too. Rows go through the same transaction, so a dry run or a failed operation leaves no trace.

Who made a change is a context value: the web app is ``APP`` by default; imports, the Strava sync and
the demo data wrap their work in ``change_source(...)`` / ``@from_source(...)``. ``via`` names the operation (e.g.
``groupset.import``) when one is known.
"""
from __future__ import annotations

import contextvars
import functools
import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, DISPOSITIONS
from bikelog.models import Bike, ChangeLog, Component, Installation, Product
from bikelog.timeutil import utc_now

SOURCES = {
    "APP": "You (app)",
    "STRAVA": "Strava sync",
    "CSV_IMPORT": "CSV import",
    "PRODUCT_IMPORT": "JSON product import",
    "DEMO": "Demo data",
    "SAMPLE": "Sample data",
    "SYSTEM": "Bike Log",
}
_ctx: contextvars.ContextVar[tuple[str, str | None]] = contextvars.ContextVar("bikelog_change_source",
                                                                             default=("APP", None))

# fields that are bookkeeping, not something the user changed
_SKIP = {"id", "uuid", "created_at", "updated_at", "disposition_on", "purchase_session_id", "from_stock_txn_id"}
LABELS = {
    "name": "name", "maker": "maker", "model": "model", "year": "year", "status": "status",
    "strava_gear_id": "Strava gear id", "notes": "notes", "purchase_price_cents": "purchase price",
    "purchase_date": "purchase date", "label": "label", "product_id": "product", "serial_number": "serial number",
    "prior_usage": "history before tracking", "price_cents": "price", "retired_on": "retired on",
    "retire_reason": "retire reason", "disposition": "state when not installed", "storage_location": "stored at",
    "tire_setup": "tire setup", "bundle_id": "bought in bundle", "component_type": "type",
}
_SETUP = {"TUBE": "inner tube", "TUBELESS": "tubeless (sealant)", "TUBULAR": "tubular"}
_PRIOR = {"NEW": "new", "RECORDED": "recorded", "UNKNOWN": "unknown"}


@contextmanager
def change_source(source: str, via: str | None = None) -> Iterator[None]:
    token = _ctx.set((source, via))
    try:
        yield
    finally:
        _ctx.reset(token)


def from_source(source: str):
    """Decorator: everything the function changes is logged as made by ``source``."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*a, **kw):
            with change_source(source, fn.__module__.rsplit(".", 1)[-1]):
                return fn(*a, **kw)
        return inner
    return wrap


def set_via(via: str | None) -> contextvars.Token:
    return _ctx.set((_ctx.get()[0], via))


def reset(token: contextvars.Token) -> None:
    _ctx.reset(token)


def _euro(cents) -> str | None:
    return None if cents is None else f"€{cents / 100:,.2f}"


def _fmt(session: Session, field: str, value) -> str | None:
    if value is None or value == "":
        return None
    if field.endswith("_cents"):
        return _euro(value)
    if field == "product_id":
        p = session.get(Product, value)
        return " ".join(x for x in (p.maker, p.model) if x) if p else f"#{value}"
    if field == "bundle_id":
        from bikelog.models import PurchaseBundle
        b = session.get(PurchaseBundle, value)
        return b.name if b else f"#{value}"
    if field == "tire_setup":
        return _SETUP.get(value, value)
    if field == "prior_usage":
        return _PRIOR.get(value, value)
    if field == "disposition":
        return DISPOSITIONS.get(value, value.replace("_", " ").lower())
    if field == "status":
        return value.lower()
    if field == "component_type":
        t = COMPONENT_TYPES.get(value)
        return t.name if t else value
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _changes(session: Session, obj) -> list[tuple[str, str | None, str | None]]:
    out = []
    state = inspect(obj)
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in _SKIP:
            continue
        hist = state.attrs[key].history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        if old == new:
            continue
        if key == "specs_json":
            out += _spec_changes(old, new)
            continue
        o, n = _fmt(session, key, old), _fmt(session, key, new)
        if o != n:
            out.append((LABELS.get(key, key.replace("_", " ")), o, n))
    return out


def _spec_changes(old: str | None, new: str | None) -> list[tuple[str, str | None, str | None]]:
    a, b = json.loads(old or "{}"), json.loads(new or "{}")
    rows = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            rows.append((f"spec: {k.replace('_', ' ')}", None if a.get(k) is None else str(a.get(k)),
                         None if b.get(k) is None else str(b.get(k))))
    return rows


def _where(session: Session, inst: Installation) -> str:
    if inst.bike_id:
        b = session.get(Bike, inst.bike_id)
        target = b.name if b else f"bike #{inst.bike_id}"
    else:
        c = session.get(Component, inst.parent_component_id)
        target = c.label if c else f"part #{inst.parent_component_id}"
    return f"{target} ({inst.slot.replace('_', ' ').lower()})"


def _installation_rows(session: Session, inst: Installation, is_new: bool) -> list[dict]:
    base = {"component_id": inst.component_id, "bike_id": inst.bike_id}
    if is_new:
        rows = [{**base, "action": "INSTALLED", "field": None, "old_value": None,
                 "new_value": f"{_where(session, inst)} from {inst.installed_at}"}]
        if inst.removed_at:
            rows.append({**base, "action": "REMOVED", "field": None, "old_value": _where(session, inst),
                         "new_value": f"on {inst.removed_at}"})
        return rows
    state = inspect(inst)
    rows = []

    def changed(key):
        h = state.attrs[key].history
        return (h.deleted[0] if h.deleted else None, h.added[0] if h.added else None) if h.has_changes() else None

    if (v := changed("voided_at")) and v[1]:
        rows.append({**base, "action": "VOIDED", "field": "installation", "old_value": _where(session, inst),
                     "new_value": f"entry was wrong: {inst.void_reason or ''}".strip(": ")})
        return rows
    if (r := changed("removed_at")) is not None:
        if r[1] and not r[0]:
            outcome = DISPOSITIONS.get(inst.removal_outcome or "", (inst.removal_outcome or "").replace("_", " ").lower())
            rows.append({**base, "action": "REMOVED", "field": None, "old_value": _where(session, inst),
                         "new_value": f"on {r[1]}" + (f" · {outcome}" if outcome else "")})
        elif r[0] and not r[1]:
            rows.append({**base, "action": "REINSTATED", "field": None, "old_value": f"removed {r[0]}",
                         "new_value": _where(session, inst)})
        else:
            rows.append({**base, "action": "CHANGED", "field": "removed on", "old_value": r[0], "new_value": r[1]})
    if (i := changed("installed_at")) is not None and i[0] is not None:
        rows.append({**base, "action": "CHANGED", "field": "installed on", "old_value": i[0], "new_value": i[1]})
    return rows


def _after_flush(session: Session, _ctx_flush) -> None:
    source, via = _ctx.get()
    rows: list[dict] = []
    with session.no_autoflush:
        for obj in list(session.new):
            if isinstance(obj, Bike):
                rows.append({"bike_id": obj.id, "component_id": None, "action": "CREATED", "field": None,
                             "old_value": None, "new_value": obj.name})
            elif isinstance(obj, Component):
                t = COMPONENT_TYPES.get(obj.component_type)
                rows.append({"bike_id": None, "component_id": obj.id, "action": "CREATED", "field": None,
                             "old_value": None, "new_value": f"{t.name if t else obj.component_type} {obj.label}"})
            elif isinstance(obj, Installation) and not obj.voided_at:
                rows += _installation_rows(session, obj, True)
        for obj in list(session.deleted):
            if isinstance(obj, Component):  # only parts without any history can be deleted (typos)
                rows.append({"bike_id": None, "component_id": obj.id, "action": "DELETED", "field": None,
                             "old_value": obj.label, "new_value": None})
        for obj in list(session.dirty):
            if isinstance(obj, (Bike, Component)):
                if not session.is_modified(obj, include_collections=False):
                    continue
                key = "bike_id" if isinstance(obj, Bike) else "component_id"
                for field, old, new in _changes(session, obj):
                    rows.append({"bike_id": None, "component_id": None, key: obj.id, "action": "CHANGED",
                                 "field": field, "old_value": old, "new_value": new})
            elif isinstance(obj, Installation):
                rows += _installation_rows(session, obj, False)
    if not rows:
        return
    now = utc_now()
    for r in rows:
        r.update(changed_at=now, source=source, via=via)
    session.connection().execute(ChangeLog.__table__.insert(), rows)


event.listen(Session, "after_flush", _after_flush)


def entries(session: Session, *, bike_id: int | None = None, component_id: int | None = None,
            limit: int = 500) -> list[dict]:
    q = select(ChangeLog)
    if bike_id is not None:
        q = q.where(ChangeLog.bike_id == bike_id)
    if component_id is not None:
        q = q.where(ChangeLog.component_id == component_id)
    q = q.order_by(ChangeLog.id.desc()).limit(limit)
    labels = dict(session.execute(select(Component.id, Component.label)).all())
    return [{"id": c.id, "changed_at": c.changed_at, "action": c.action, "field": c.field,
             "old_value": c.old_value, "new_value": c.new_value, "source": c.source,
             "who": SOURCES.get(c.source, c.source), "via": c.via,
             "component_id": c.component_id, "component": labels.get(c.component_id) if bike_id is not None else None}
            for c in session.scalars(q)]
