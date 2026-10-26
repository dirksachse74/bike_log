"""Every bike has a frame (with its fork, one piece) as a part (DECISIONS 96 and 98).

The bike is the build: its name, Strava gear, rides and total km. The frame is a part on it with its own
km, serial number and warranty date, so a warranty frame (Replace, old one "returned under warranty")
starts at 0 km while the bike keeps its history, and a frame moved to another build takes its km along.
Dirk keeps frame and fork as one piece; the separate fork parts an earlier build added automatically are
removed again when nothing was recorded on them (drop_auto_forks). Bikes get the frame automatically: from the bike's first day (purchase date, starting km or first
ride, whichever is earliest), with the bike's starting km. While such an automatic installation is the
only one, it follows the bike's start when older rides arrive later (a Strava sync, a CSV import).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.models import Bike, Component, Installation, Ride, UsageAdjustment
from bikelog.services import inventory as inv
from bikelog.services import settings
from bikelog.timeutil import local_date_of, parse_when

AUTO_NOTE = "Added with the bike (frame and fork are parts)"
PARTS = (("FRAME", "frame"),)


def _start(session: Session, bike: Bike) -> str:
    tz = settings.tz(session)
    days = [bike.purchase_date]
    try:
        days.append(local_date_of(bike.created_at, tz))
    except (TypeError, ValueError):   # very old records may lack a proper timestamp
        pass
    first = session.scalar(select(func.min(Ride.sort_utc)).where(Ride.bike_id == bike.id))
    if first:
        days.append(local_date_of(first, tz))
    adj = _bike_start(session, bike)
    if adj:
        days.append(local_date_of(adj.effective_utc, tz))
    return min(d for d in days if d)


def _bike_start(session: Session, bike: Bike) -> UsageAdjustment | None:
    return session.scalar(select(UsageAdjustment).where(UsageAdjustment.bike_id == bike.id,
                                                        UsageAdjustment.kind == "STARTING",
                                                        UsageAdjustment.voided_at.is_(None)))


def _label(session: Session, ctype: str, base: str) -> str:
    label, n = base, 2
    while session.scalar(select(Component.id).where(Component.component_type == ctype,
                                                    func.lower(Component.label) == label.lower())):
        label, n = f"{base} ({n})", n + 1
    return label


def ensure_frames(session: Session, bike_id: int | None = None) -> int:
    """Add the missing frame / fork parts and move automatic ones back to the bike's start. Returns how
    many parts were added or moved. A bike that ever had a frame (or fork) installed is left alone for it."""
    changed = drop_auto_forks(session)
    q = select(Bike).where(Bike.status == "ACTIVE")
    if bike_id is not None:
        q = q.where(Bike.id == bike_id)
    for bike in list(session.scalars(q)):
        start = _start(session, bike)
        for ctype, word in PARTS:
            rows = list(session.scalars(select(Installation).join(Component, Component.id == Installation.component_id)
                                        .where(Installation.bike_id == bike.id, Component.component_type == ctype)))
            if rows:
                changed += _follow_start(session, rows, start)
                continue
            adj = _bike_start(session, bike)
            comp = inv.create_component(session, component_type=ctype, label=_label(session, ctype, f"{bike.name} {word}"),
                                        prior_usage="RECORDED" if adj else "UNKNOWN")
            inv.install(session, comp.id, at=start, bike_id=bike.id, slot=ctype, note=AUTO_NOTE, reallocate=False)
            if adj:   # the bike's odometer at its start is the frame's (and fork's) too
                session.add(UsageAdjustment(component_id=comp.id, kind="STARTING", effective_at=adj.effective_at,
                                            effective_utc=adj.effective_utc, km=adj.km, is_estimate=adj.is_estimate,
                                            note=f"from {bike.name}'s starting km"))
            changed += 1
    if changed:
        session.flush()
        inv._reallocate(session)
    return changed


def _follow_start(session: Session, rows: list[Installation], start: str) -> int:
    """The automatic installation, while it is the part's only one, starts with the bike."""
    if len(rows) != 1:
        return 0
    i = rows[0]
    if i.note != AUTO_NOTE or i.voided_at or i.removed_utc:
        return 0
    if session.scalar(select(func.count()).select_from(Installation).where(Installation.component_id == i.component_id)) != 1:
        return 0
    w = parse_when(start, settings.tz(session))
    if w.utc >= i.installed_utc:
        return 0
    i.installed_at, i.installed_utc = w.raw, w.utc
    return 1


def frame_history(session: Session, comp: Component) -> dict:
    """Frame inspections and crashes of the bikes this frame (or fork) was on, while it was on them."""
    from bikelog.services import incidents
    from bikelog.services import maintenance as m
    periods = [(i.bike_id, i.installed_at[:10], (i.removed_at or "9999-12-31")[:10])
               for i in session.scalars(select(Installation).where(Installation.component_id == comp.id,
                                                                  Installation.voided_at.is_(None),
                                                                  Installation.bike_id.is_not(None)))]

    def during(bike_id: int | None, day: str) -> bool:
        return any(b == bike_id and start <= day < end for b, start, end in periods)
    inspections, crashes = [], []
    for bike_id in {p[0] for p in periods}:
        for e in m.events_for(session, bike_id=bike_id):
            if e["component_id"] is None and e["action_code"] == "FRAME_INSPECT" and not e["voided"] \
                    and during(bike_id, e["performed_on"]):
                inspections.append(e)
        for r in incidents.all_incidents(session, bike_id=bike_id, incident_type="CRASH"):
            if during(bike_id, r["on"]):
                crashes.append(r)
    inspections.sort(key=lambda e: e["performed_at"], reverse=True)
    crashes.sort(key=lambda r: r["on"], reverse=True)
    return {"inspections": inspections, "crashes": crashes}


def drop_auto_forks(session: Session) -> int:
    """Remove fork parts that were only ever the automatic one on a bike (commit 9842a2a added them; Dirk
    keeps frame and fork as one piece). A fork with anything of its own (another installation, work, a
    note, a status change, a repair, a price, serial or warranty) stays."""
    from bikelog.models import (ComponentDisposition, JournalEntry, MaintenanceEvent, ServiceOrder,
                                UsageContribution)
    dropped = 0
    for comp in list(session.scalars(select(Component).where(Component.component_type == "FORK"))):
        insts = list(session.scalars(select(Installation).where(Installation.component_id == comp.id)))
        if len(insts) != 1 or insts[0].note != AUTO_NOTE or insts[0].removed_utc or insts[0].voided_at:
            continue
        if comp.price_cents is not None or comp.serial_number or comp.warranty_until or comp.bundle_id \
                or comp.product_id or comp.notes or comp.mark:
            continue
        owned = any(session.scalar(select(func.count()).select_from(model).where(col == comp.id))
                    for model, col in ((MaintenanceEvent, MaintenanceEvent.component_id),
                                       (JournalEntry, JournalEntry.component_id),
                                       (ComponentDisposition, ComponentDisposition.component_id),
                                       (ServiceOrder, ServiceOrder.component_id),
                                       (ServiceOrder, ServiceOrder.replacement_id),
                                       (Installation, Installation.parent_component_id)))
        if owned:
            continue
        session.query(UsageContribution).filter(UsageContribution.component_id == comp.id).delete()
        session.query(UsageAdjustment).filter(UsageAdjustment.component_id == comp.id).delete()
        session.delete(insts[0])
        session.flush()
        session.delete(comp)
        dropped += 1
    if dropped:
        session.flush()
    return dropped
