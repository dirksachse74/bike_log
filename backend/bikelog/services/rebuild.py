"""Recompute derived values: ordering instants after a timezone change, then all contributions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.models import Installation, MaintenanceEvent, Ride, UsageAdjustment
from bikelog.services import allocation, settings
from bikelog.timeutil import parse_when


def recompute_instants(session: Session) -> None:
    """Date-only values mean 'start of the local day'; their UTC instants depend on the timezone."""
    tz = settings.tz(session)
    for r in session.scalars(select(Ride)):
        if r.start_time_utc is None:
            r.sort_utc = parse_when(r.ride_date, tz).utc
        else:
            r.ride_date = parse_when(r.start_time_utc, tz).local_date
    for i in session.scalars(select(Installation)):
        i.installed_utc = parse_when(i.installed_at, tz).utc
        if i.removed_at:
            i.removed_utc = parse_when(i.removed_at, tz).utc
    for e in session.scalars(select(MaintenanceEvent)):
        w = parse_when(e.performed_at, tz)
        e.sort_utc, e.performed_on = w.utc, w.local_date
    for a in session.scalars(select(UsageAdjustment)):
        a.effective_utc = parse_when(a.effective_at, tz).utc
    session.flush()


def rebuild_everything(session: Session) -> int:
    recompute_instants(session)
    return allocation.rebuild_all(session, settings.tz(session))
