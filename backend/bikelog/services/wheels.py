"""A wheelset always has a front and a rear wheel (DECISIONS 108).

Tires, tubes, rotors, cassettes and hubs mount on a wheel. A wheelset added on its own (Add part →
Wheelset) had no wheels inside, so a tire had nowhere to go ("Pick where the tire goes" with nothing to
pick). ``ensure_wheels`` adds the missing front / rear wheel records inside such a wheelset, from the
wheelset's first day, with its starting km, so they share its history. A wheelset that ever had a wheel in
that position is left alone (a wheel taken out on purpose is not put back).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.models import Component, Installation, UsageAdjustment
from bikelog.services import inventory as inv
from bikelog.services import settings
from bikelog.timeutil import local_date_of

AUTO_NOTE = "Added with the wheelset (a wheelset has a front and a rear wheel)"
WHEELS = (("FRONT_WHEEL", "front wheel"), ("REAR_WHEEL", "rear wheel"))


def _first_day(session: Session, ws: Component) -> str:
    first = session.scalar(select(Installation).where(Installation.component_id == ws.id,
                                                      Installation.voided_at.is_(None))
                           .order_by(Installation.installed_utc).limit(1))
    if first is not None:
        return first.installed_at
    tz = settings.tz(session)
    days = [ws.purchase_date]
    try:
        days.append(local_date_of(ws.created_at, tz))
    except (TypeError, ValueError):
        pass
    return min(d for d in days if d)


def ensure_wheels(session: Session, wheelset_id: int | None = None) -> int:
    """Add the missing wheel records inside wheelsets; returns how many were added."""
    q = select(Component).where(Component.component_type == "WHEELSET", Component.status == "ACTIVE")
    if wheelset_id is not None:
        q = q.where(Component.id == wheelset_id)
    added = 0
    for ws in list(session.scalars(q)):
        for ctype, word in WHEELS:
            ever = session.scalar(select(Installation.id).where(Installation.parent_component_id == ws.id,
                                                                Installation.slot == ctype,
                                                                Installation.voided_at.is_(None)).limit(1))
            if ever is not None:
                continue
            start = session.scalar(select(UsageAdjustment).where(UsageAdjustment.component_id == ws.id,
                                                                 UsageAdjustment.kind == "STARTING",
                                                                 UsageAdjustment.voided_at.is_(None)))
            wheel = inv.create_component(session, component_type=ctype, label=f"{ws.label} {word}",
                                         prior_usage=ws.prior_usage, purchase_date=ws.purchase_date)
            wheel.notes = AUTO_NOTE
            inv.install(session, wheel.id, at=_first_day(session, ws), parent_component_id=ws.id, slot=ctype,
                        note=AUTO_NOTE, reallocate=False)
            if start is not None:   # the wheelset's km from before are the wheels' too
                session.add(UsageAdjustment(component_id=wheel.id, kind="STARTING", effective_at=start.effective_at,
                                            effective_utc=start.effective_utc, km=start.km,
                                            is_estimate=start.is_estimate, note=f"from {ws.label}'s starting km"))
            added += 1
    if added:
        session.flush()
        inv._reallocate(session)
    return added


def tire_and_tube(session: Session, wheel: Component) -> dict:
    """The wheel page's "Tire and inner tube" card (Dirk 2026-11-02): per kind the one on the wheel now and every
    one that was on it, newest first, each with its own km (on this wheel and in total), its punctures and how it
    came off. A tube's km are the rides from its install day on until it came off."""
    from sqlalchemy import func

    from bikelog.catalog import DISPOSITIONS
    from bikelog.models import JournalEntry, UsageContribution
    from bikelog.services.usage import component_usage

    out: dict[str, dict] = {}
    for ctype in ("TIRE", "INNER_TUBE"):
        rows = []
        for i in session.scalars(select(Installation).join(Component, Component.id == Installation.component_id)
                                 .where(Installation.parent_component_id == wheel.id,
                                        Installation.voided_at.is_(None), Component.component_type == ctype)
                                 .order_by(Installation.installed_utc.desc())):
            c = session.get(Component, i.component_id)
            here = session.scalar(select(func.sum(UsageContribution.km)).where(
                UsageContribution.component_id == c.id, UsageContribution.state == "COUNTED",
                UsageContribution.sort_utc >= i.installed_utc,
                UsageContribution.sort_utc < (i.removed_utc or "9999"))) or 0
            flats = session.scalar(select(func.count(func.distinct(JournalEntry.incident_group))).where(
                JournalEntry.component_id == c.id, JournalEntry.incident_type == "FLAT",
                JournalEntry.voided_at.is_(None))) or 0
            ended = None
            if i.removed_at is not None:
                ended = i.removal_reason or ("moved" if inv.open_installation(session, c.id) else None)
                if c.disposition not in ("INSTALLED", "STORED") and c.disposition in DISPOSITIONS:
                    ended = f"{ended + ' · ' if ended else ''}{DISPOSITIONS[c.disposition].lower()}"
            rows.append({"component_id": c.id, "label": c.label, "installed_at": i.installed_at,
                         "removed_at": i.removed_at, "km_here": round(float(here), 1),
                         "km_total": round(component_usage(session, c)["total_km"], 1),
                         "punctures": flats, "ended": ended, "current": i.removed_at is None})
        out[ctype] = {"current": next((r for r in rows if r["current"]), None),
                      "history": rows}
    return out
