"""Component and bike usage read from contributions + starting values. Honest about what is known."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.models import Bike, Component, Ride, UsageAdjustment, UsageContribution


def _round(x: float) -> float:
    return round(x + 0.0, 6)  # display rounding happens in the UI


def starting_value(session: Session, component_id: int | None = None, bike_id: int | None = None) -> UsageAdjustment | None:
    q = select(UsageAdjustment).where(UsageAdjustment.kind == "STARTING", UsageAdjustment.voided_at.is_(None))
    q = q.where(UsageAdjustment.component_id == component_id) if component_id else q.where(UsageAdjustment.bike_id == bike_id)
    return session.scalars(q.order_by(UsageAdjustment.id.desc())).first()


def component_totals(session: Session, component_ids: list[int] | None = None) -> dict[int, float]:
    """Total km per component (starting value + corrections + counted rides). Used for change deltas."""
    q = select(UsageContribution.component_id, func.sum(UsageContribution.km)).where(
        UsageContribution.state == "COUNTED").group_by(UsageContribution.component_id)
    if component_ids is not None:
        q = q.where(UsageContribution.component_id.in_(component_ids))
    out = {cid: float(km or 0) for cid, km in session.execute(q)}
    aq = select(UsageAdjustment.component_id, func.sum(UsageAdjustment.km)).where(
        UsageAdjustment.voided_at.is_(None), UsageAdjustment.component_id.is_not(None)).group_by(UsageAdjustment.component_id)
    if component_ids is not None:
        aq = aq.where(UsageAdjustment.component_id.in_(component_ids))
    for cid, km in session.execute(aq):
        out[cid] = out.get(cid, 0.0) + float(km or 0)
    return {k: _round(v) for k, v in out.items()}


def component_usage(session: Session, comp: Component) -> dict:
    rows = session.execute(
        select(UsageContribution.certain, func.sum(UsageContribution.km), func.sum(UsageContribution.duration_s),
               func.count()).where(UsageContribution.component_id == comp.id, UsageContribution.state == "COUNTED")
        .group_by(UsageContribution.certain)).all()
    ride_km_certain = sum(float(r[1] or 0) for r in rows if r[0])
    ride_km_uncertain = sum(float(r[1] or 0) for r in rows if not r[0])
    seconds = sum(int(r[2] or 0) for r in rows)
    ride_count = sum(int(r[3]) for r in rows)
    missing_distance = session.scalar(
        select(func.count()).select_from(UsageContribution).join(Ride, Ride.id == UsageContribution.ride_id)
        .where(UsageContribution.component_id == comp.id, UsageContribution.state == "COUNTED",
               Ride.distance_km.is_(None))) or 0
    adjustments = list(session.scalars(select(UsageAdjustment).where(
        UsageAdjustment.component_id == comp.id, UsageAdjustment.voided_at.is_(None)).order_by(UsageAdjustment.effective_utc)))
    start = next((a for a in reversed(adjustments) if a.kind == "STARTING"), None)
    corrections = [a for a in adjustments if a.kind == "CORRECTION"]
    start_km = start.km if start else 0.0
    corr_km = sum(a.km for a in corrections)
    total = start_km + corr_km + ride_km_certain + ride_km_uncertain

    if start and start.is_estimate:
        certainty = "ESTIMATED"
    elif comp.prior_usage == "UNKNOWN" and not start:
        certainty = "INCOMPLETE"
    elif ride_km_uncertain > 0 or missing_distance:
        certainty = "PARTLY_UNCERTAIN"
    else:
        certainty = "KNOWN"
    parts = []
    if start:
        parts.append(f"{'≈' if start.is_estimate else ''}{start_km:,.0f} km {'estimated ' if start.is_estimate else ''}"
                     f"starting value as of {start.effective_at[:10]}")
    elif comp.prior_usage == "UNKNOWN":
        parts.append("usage before tracking is unknown (total is a minimum)")
    parts.append(f"{ride_km_certain + ride_km_uncertain:,.1f} km from {ride_count} ride{'s' if ride_count != 1 else ''}")
    if ride_km_uncertain:
        parts.append(f"{ride_km_uncertain:,.1f} km of it uncertain")
    if corrections:
        parts.append(f"{corr_km:+,.1f} km corrections")
    if missing_distance:
        parts.append(f"{missing_distance} ride(s) with missing distance")
    return {
        "total_km": _round(total),
        "ride_km": _round(ride_km_certain + ride_km_uncertain),
        "uncertain_km": _round(ride_km_uncertain),
        "starting_km": start_km if start else None,
        "starting_is_estimate": bool(start and start.is_estimate),
        "starting_effective": start.effective_at if start else None,
        "correction_km": _round(corr_km),
        "ride_count": ride_count,
        "hours": round(seconds / 3600, 2),
        "missing_distance_rides": missing_distance,
        "certainty": certainty,
        "is_minimum": comp.prior_usage == "UNKNOWN" and not start,
        "summary": "; ".join(parts),
    }


def component_ledger(session: Session, comp: Component) -> list[dict]:
    """Every contribution behind a component's mileage, oldest first, with a running total."""
    rows = session.execute(
        select(UsageContribution, Ride, Bike.name).join(Ride, Ride.id == UsageContribution.ride_id)
        .join(Bike, Bike.id == UsageContribution.bike_id)
        .where(UsageContribution.component_id == comp.id).order_by(UsageContribution.sort_utc, Ride.id)).all()
    entries: list[dict] = []
    for a in session.scalars(select(UsageAdjustment).where(
            UsageAdjustment.component_id == comp.id, UsageAdjustment.voided_at.is_(None))):
        entries.append({"kind": a.kind, "sort": a.effective_utc, "date": a.effective_at[:10], "km": a.km,
                        "counted": True, "certain": not a.is_estimate, "is_estimate": a.is_estimate,
                        "detail": a.note or ("Starting value" if a.kind == "STARTING" else "Correction")})
    for c, r, bike_name in rows:
        entries.append({"kind": "RIDE", "sort": c.sort_utc, "date": r.ride_date, "km": c.km, "ride_id": r.id,
                        "ride_name": r.name, "bike": bike_name, "slot": c.slot, "basis": c.basis,
                        "counted": c.state == "COUNTED", "state": c.state, "certain": c.certain,
                        "detail": c.note, "duration_s": c.duration_s})
    entries.sort(key=lambda e: (e["sort"], 0 if e["kind"] == "STARTING" else 1))
    running = 0.0
    for e in entries:
        if e["counted"]:
            running += e["km"]
        e["running_km"] = _round(running)
        del e["sort"]
    return entries


def bike_usage(session: Session, bike: Bike) -> dict:
    row = session.execute(select(func.sum(Ride.distance_km), func.sum(Ride.duration_s), func.count()).where(
        Ride.bike_id == bike.id, Ride.status == "ACTIVE", Ride.inclusion == "INCLUDED")).one()
    start = starting_value(session, bike_id=bike.id)
    ride_km = float(row[0] or 0)
    if start:
        before = session.scalar(select(func.sum(Ride.distance_km)).where(
            Ride.bike_id == bike.id, Ride.status == "ACTIVE", Ride.inclusion == "INCLUDED",
            Ride.sort_utc < start.effective_utc)) or 0.0
        ride_km -= float(before)
    total = (start.km if start else 0.0) + ride_km
    return {
        "total_km": _round(total), "ride_km": _round(ride_km), "ride_count": int(row[2]),
        "hours": round((row[1] or 0) / 3600, 2),
        "starting_km": start.km if start else None, "starting_is_estimate": bool(start and start.is_estimate),
        "starting_effective": start.effective_at if start else None,
        "certainty": "ESTIMATED" if start and start.is_estimate else ("KNOWN" if start else "INCOMPLETE"),
    }


def usage_since(session: Session, component_id: int, since_utc: str | None) -> float:
    q = select(func.sum(UsageContribution.km)).where(
        UsageContribution.component_id == component_id, UsageContribution.state == "COUNTED")
    if since_utc:
        q = q.where(UsageContribution.sort_utc >= since_utc)
    return _round(float(session.scalar(q) or 0))
