"""Part life report (DECISIONS 99): how long your parts lasted, per part type and per product.

A part is finished when it is out of use for good (worn out and discarded, retired, sold, returned under
warranty). For each finished part: lifetime km and ride hours, months in use (first installation to the
day it went), product, the bikes it was on and why it went. Products get an average over their finished
parts. Every number says whether it is known or estimated: km from before Bike Log (an estimated starting
value), rides with an uncertain bike, or an unknown earlier history make it an estimate or a minimum.
Parts still in use are listed apart with their km so far; they are never part of an average.
Nothing here is stored: it is computed from installations, usage and dispositions on every call."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, DISPOSITIONS, OUT_OF_USE
from bikelog.models import Bike, Component, Installation
from bikelog.services import settings
from bikelog.services.usage import component_usage
from bikelog.timeutil import local_date_of, today_local

# types where "how long did it last" is not a question worth a report
SKIP_TYPES = ("FRAME", "FORK")


def _months(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    d = (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
    return round(max(d, 0) / 30.44, 1)


def _row(session: Session, comp: Component, tz: str, today: str, bikes: dict[int, str]) -> dict:
    u = component_usage(session, comp)
    insts = list(session.scalars(select(Installation).where(Installation.component_id == comp.id,
                                                            Installation.voided_at.is_(None))
                                 .order_by(Installation.installed_utc)))
    first = local_date_of(insts[0].installed_utc, tz) if insts else None
    bike_ids = []
    for i in insts:
        bid = i.bike_id
        if bid is None and i.parent_component_id:   # on a wheel / wheelset: the bike that carried the parent
            parent = session.scalar(select(Installation.bike_id).where(
                Installation.component_id == i.parent_component_id, Installation.voided_at.is_(None),
                Installation.bike_id.is_not(None), Installation.installed_utc <= i.installed_utc)
                .order_by(Installation.installed_utc.desc()).limit(1))
            bid = parent
        if bid is not None and bid not in bike_ids:
            bike_ids.append(bid)
    finished = comp.status == "RETIRED" and comp.disposition in OUT_OF_USE
    ended = comp.retired_on if finished else None
    last_removal = next((i for i in reversed(insts) if i.removed_utc), None)
    if finished and last_removal is not None:
        ended = local_date_of(last_removal.removed_utc, tz)   # it stopped being used when it came off
    why = None
    if finished:
        why = DISPOSITIONS.get(comp.disposition, comp.disposition)
        detail = comp.retire_reason if comp.retire_reason and comp.retire_reason.lower() != why.lower() else None
        if last_removal is not None and last_removal.removal_reason and not detail:
            detail = last_removal.removal_reason
        if detail:
            why += f" ({detail})"
    p = comp.product
    return {"component_id": comp.id, "label": comp.label, "component_type": comp.component_type,
            "product_id": comp.product_id,
            "product": f"{p.maker or ''} {p.model}".strip() if p else None,
            "bikes": [bikes.get(b, f"#{b}") for b in bike_ids],
            "first_installed": first, "ended": ended, "finished": finished,
            "months": _months(first, ended or today) if first else None,
            "km": u["total_km"], "hours": u["hours"], "rides": u["ride_count"],
            "certainty": u["certainty"], "is_minimum": u["is_minimum"],
            "estimated": u["certainty"] != "KNOWN", "why": why}


def _average(rows: list[dict]) -> dict:
    km = [r["km"] for r in rows]
    hours = [r["hours"] for r in rows if r["hours"]]
    months = [r["months"] for r in rows if r["months"] is not None]
    return {"count": len(rows), "avg_km": round(sum(km) / len(km)) if km else None,
            "min_km": round(min(km)) if km else None, "max_km": round(max(km)) if km else None,
            "avg_hours": round(sum(hours) / len(hours), 1) if hours else None,
            "avg_months": round(sum(months) / len(months), 1) if months else None,
            "estimated": any(r["estimated"] for r in rows),
            "minimum": any(r["is_minimum"] for r in rows)}


def report(session: Session, component_type: str | None = None) -> dict:
    """Per part type: finished parts, products with their average, and the parts still in use."""
    tz = settings.tz(session)
    today = today_local(tz).isoformat()
    bikes = dict(session.execute(select(Bike.id, Bike.name)).all())
    q = select(Component).where(Component.disposition != "VOIDED", Component.component_type.not_in(SKIP_TYPES))
    if component_type:
        q = q.where(Component.component_type == component_type)
    by_type: dict[str, dict[str, list]] = defaultdict(lambda: {"finished": [], "in_use": []})
    for comp in session.scalars(q.order_by(Component.label)):
        used = session.scalar(select(Installation.id).where(Installation.component_id == comp.id,
                                                            Installation.voided_at.is_(None)).limit(1))
        if used is None and comp.disposition != "IN_USE":
            continue                       # never on a bike: nothing to say about its life
        r = _row(session, comp, tz, today, bikes)
        by_type[comp.component_type]["finished" if r["finished"] else "in_use"].append(r)
    types = []
    for code, g in by_type.items():
        t = COMPONENT_TYPES.get(code)
        products: dict[tuple, list] = defaultdict(list)
        for r in g["finished"]:
            products[(r["product_id"], r["product"])].append(r)
        prods = [{"product_id": pid, "product": name or "No product recorded", **_average(rows)}
                 for (pid, name), rows in products.items()]
        prods.sort(key=lambda p: (-p["count"], p["product"]))
        g["finished"].sort(key=lambda r: r["ended"] or "", reverse=True)
        g["in_use"].sort(key=lambda r: -r["km"])
        types.append({"code": code, "name": t.name if t else code, "category": t.category if t else None,
                      "finished": g["finished"], "in_use": g["in_use"], "products": prods,
                      "overall": _average(g["finished"]) if g["finished"] else None})
    types.sort(key=lambda t: (-len(t["finished"]), t["name"]))
    return {"types": types}

