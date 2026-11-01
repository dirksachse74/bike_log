"""Reusable pick lists (DECISIONS 106): names you pick from a dropdown instead of typing them again.

The first list is SHOP (where you bought a part, a bike, stock; where a part went for repair). Records keep
the name as text in their own column (``LISTS[code]["columns"]``); the list holds the names on offer.

* Saving any record with a name (typed or picked) puts it on the list if it is new, and a name that differs
  only in upper/lower case, or that was merged into another, is stored as the list's name (before_flush
  hook below), so "bike-components.de" and "Bike-Components.de" never become two shops.
* Settings → Lists: add, rename (every record using the name follows, each change in the change log),
  merge duplicates (the records move to the kept name; the other entry stays, marked merged), hide (gone
  from the dropdowns, records keep it). Nothing is deleted.

A new list: add an entry to LISTS with the columns that hold its names; the hook, the API
(``/api/lists``) and the Settings section pick it up.
"""
from __future__ import annotations

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from bikelog.models import Bike, Component, ConsumableTxn, PickListItem, PurchaseBundle, ServiceOrder
from bikelog.services.errors import Conflict, DomainError, NotFound
from bikelog.timeutil import utc_now

LISTS: dict[str, dict] = {
    "SHOP": {
        "name": "Shops",
        "hint": "Where you buy parts, bikes and supplies, and where parts go for repair.",
        "columns": [(Component, "shop"), (Bike, "shop"), (ConsumableTxn, "shop"), (PurchaseBundle, "merchant"),
                    (ServiceOrder, "shop")],
    },
}


def _check(code: str) -> dict:
    if code not in LISTS:
        raise NotFound(f"No list {code!r}")
    return LISTS[code]


def _find(session: Session, code: str, name: str) -> PickListItem | None:
    return session.scalar(select(PickListItem).where(PickListItem.list_code == code,
                                                     func.lower(PickListItem.name) == name.lower()))


def _final(session: Session, item: PickListItem) -> PickListItem:
    seen = set()
    while item.merged_into_id and item.id not in seen:
        seen.add(item.id)
        item = session.get(PickListItem, item.merged_into_id)
    return item


def canonical(session: Session, code: str, name: str | None) -> str | None:
    """The list's spelling of a name (a merged name gives the name it went into); a new name is added."""
    name = " ".join((name or "").split())
    if not name:
        return None
    with session.no_autoflush:
        item = _find(session, code, name)
        if item is None:
            pending = next((o for o in session.new if isinstance(o, PickListItem) and o.list_code == code
                            and o.name.lower() == name.lower()), None)
            if pending is not None:
                return pending.name
            session.add(PickListItem(list_code=code, name=name))
            return name
        item = _final(session, item)
        if item.hidden_at:          # used again: back in the dropdowns
            item.hidden_at = None
        return item.name


def _before_flush(session: Session, _ctx, _instances) -> None:
    for code, spec in LISTS.items():
        for cls, col in spec["columns"]:
            for obj in list(session.new) + list(session.dirty):
                if isinstance(obj, cls):
                    v = getattr(obj, col)
                    if v is not None:
                        c = canonical(session, code, v)
                        if c != v:
                            setattr(obj, col, c)


event.listen(Session, "before_flush", _before_flush)


def _uses(session: Session, code: str, name: str) -> int:
    n = 0
    for cls, col in LISTS[code]["columns"]:
        n += session.scalar(select(func.count()).select_from(cls).where(func.lower(getattr(cls, col)) == name.lower())) or 0
    return n


def _row(session: Session, item: PickListItem) -> dict:
    return {"id": item.id, "name": item.name, "hidden": item.hidden_at is not None,
            "merged_into": session.get(PickListItem, item.merged_into_id).name if item.merged_into_id else None,
            "uses": 0 if item.merged_into_id else _uses(session, item.list_code, item.name)}


def names(session: Session, code: str) -> list[str]:
    """For a dropdown: the names on offer (not hidden, not merged), A–Z."""
    _check(code)
    return list(session.scalars(select(PickListItem.name).where(
        PickListItem.list_code == code, PickListItem.hidden_at.is_(None), PickListItem.merged_into_id.is_(None))
        .order_by(func.lower(PickListItem.name))))


def overview(session: Session) -> list[dict]:
    out = []
    for code, spec in LISTS.items():
        items = session.scalars(select(PickListItem).where(PickListItem.list_code == code)
                                .order_by(func.lower(PickListItem.name)))
        out.append({"code": code, "name": spec["name"], "hint": spec["hint"],
                    "items": [_row(session, i) for i in items]})
    return out


def _item(session: Session, item_id: int) -> PickListItem:
    item = session.get(PickListItem, item_id)
    if item is None:
        raise NotFound(f"List entry {item_id} not found")
    return item


def add(session: Session, code: str, name: str) -> dict:
    _check(code)
    name = " ".join((name or "").split())
    if not name:
        raise DomainError("Enter a name")
    existing = _find(session, code, name)
    if existing is not None:
        raise Conflict(f"{existing.name!r} is already on the list" + (" (hidden)" if existing.hidden_at else ""))
    item = PickListItem(list_code=code, name=name)
    session.add(item)
    session.flush()
    return _row(session, item)


def _move_records(session: Session, code: str, old: str, new: str) -> int:
    """Every record using ``old`` gets ``new`` (through the ORM, so the change log records it)."""
    n = 0
    for cls, col in LISTS[code]["columns"]:
        for obj in session.scalars(select(cls).where(func.lower(getattr(cls, col)) == old.lower())):
            setattr(obj, col, new)
            n += 1
    return n


def rename(session: Session, item_id: int, name: str) -> dict:
    item = _item(session, item_id)
    if item.merged_into_id:
        raise DomainError(f"{item.name!r} was merged into another entry; rename that one")
    name = " ".join((name or "").split())
    if not name:
        raise DomainError("Enter a name")
    other = _find(session, item.list_code, name)
    if other is not None and other.id != item.id:
        raise Conflict(f"{other.name!r} is already on the list. To make them one, use Merge.")
    old = item.name
    item.name = name               # first, so the hook finds the new name when the records follow
    session.flush()
    _move_records(session, item.list_code, old, name)
    session.flush()
    return _row(session, item)


def set_hidden(session: Session, item_id: int, hidden: bool) -> dict:
    item = _item(session, item_id)
    item.hidden_at = utc_now() if hidden else None
    session.flush()
    return _row(session, item)


def merge(session: Session, item_id: int, into_id: int) -> dict:
    """Duplicates: the records of ``item_id`` move to ``into_id``; the entry stays, marked merged."""
    item, into = _item(session, item_id), _item(session, into_id)
    if item.id == into.id or item.list_code != into.list_code:
        raise DomainError("Pick another entry of the same list to merge into")
    into = _final(session, into)
    if into.id == item.id:
        raise DomainError("That entry was merged into this one")
    item.merged_into_id = into.id
    item.hidden_at = item.hidden_at or utc_now()
    into.hidden_at = None
    session.flush()
    moved = _move_records(session, item.list_code, item.name, into.name)
    session.flush()
    return {**_row(session, into), "moved": moved}
