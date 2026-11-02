"""Puncture statistics (Dirk 2026-11-01, DECISIONS 117): how often you flat, and with which tubes and tires.

A puncture is logged as a "Flat tire" incident on the ride (Rides → the ride → Add incident → Flat tire, per
wheel "tube only" or "tube and tire"). Here every wheel of such an incident is one puncture, with the tube
and the tire that were on that wheel that day (the damaged ones from the incident, otherwise the ones
installed), the bike, the ride's conditions (wet/dry) and what was done about it.

Per tube model and per tire model: punctures, the km all your tubes (tires) of that model have done, and km
per puncture. A model is the product (maker + model) when the part has one, else the part's name.
Tubes kept as stock ("Conti Race 28, 3 at home") have no part record: when a flat was fixed with a tube from
stock, the next flat on that bike and wheel was that tube (marked "from the last fix"), and its km are the
bike's ride km from that fix to the next flat (or to today while it is still in). Nothing is stored:
everything is computed from incidents, their fixes, installations and rides on each call.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import WHEEL_TYPES
from bikelog.models import Bike, Component, Consumable, ConsumableTxn, Installation, JournalEntry, Ride
from bikelog.services import inventory as inv
from bikelog.services import journal, settings
from bikelog.services.incidents import parts_on_ride
from bikelog.services.usage import component_usage
from bikelog.timeutil import today_local

WHEEL_NAME = {"FRONT_WHEEL": "Front", "REAR_WHEEL": "Rear"}
NOT_RECORDED = "Not recorded in Bike Log"


def model_of(comp: Component | None) -> str:
    if comp is None:
        return NOT_RECORDED
    p = comp.product
    if p is not None:
        return f"{p.maker or ''} {p.model}".strip()
    return re.sub(r"\s*\(\d+\)$", "", comp.label).strip()      # "Tube (2)" is the same model as "Tube"


def _wheel_of(session: Session, comp_id: int, day: str, depth: int = 0) -> str | None:
    """FRONT_WHEEL / REAR_WHEEL: the wheel the part sat on that day (a tube or tire on a wheel)."""
    if depth > 4:
        return None
    comp = session.get(Component, comp_id)
    if comp is not None and comp.component_type in WHEEL_TYPES:
        return comp.component_type
    insts = session.scalars(select(Installation).where(Installation.component_id == comp_id,
                                                       Installation.voided_at.is_(None))
                            .order_by(Installation.installed_utc))
    for i in insts:      # on that day, the removal day included (a tube replaced right after the flat)
        if i.installed_at[:10] <= day and (i.removed_at is None or i.removed_at[:10] >= day):
            if i.parent_component_id:
                return _wheel_of(session, i.parent_component_id, day, depth + 1)
            for w in WHEEL_TYPES:
                if i.slot and i.slot.startswith(w.split("_")[0]):
                    return w
    return None


def _wheel_from_text(text: str | None) -> str | None:
    t = (text or "").lower()
    return "FRONT_WHEEL" if t.startswith("front") else "REAR_WHEEL" if t.startswith("rear") else None


def _stock_tube_in(session: Session, ws_id: int, wheel: str | None) -> str | None:
    """The stock tube a fix put in at that wheel (the stock line's name)."""
    for t in session.scalars(select(ConsumableTxn).where(ConsumableTxn.work_session_id == ws_id,
                                                         ConsumableTxn.kind == "USE",
                                                         ConsumableTxn.voided_at.is_(None))):
        line = session.get(Consumable, t.consumable_id)
        if line is None or line.component_type != "INNER_TUBE":
            continue
        if wheel is None or f": {WHEEL_NAME.get(wheel, '').lower()} " in (t.note or "").lower():
            return line.name
    return None


def _bike_km(session: Session, bike_id: int | None, after: str, until: str) -> float:
    if bike_id is None:
        return 0.0
    return sum(r.distance_km or 0 for r in session.scalars(select(Ride).where(
        Ride.bike_id == bike_id, Ride.status == "ACTIVE", Ride.ride_date > after, Ride.ride_date <= until)))


def _collect(session: Session) -> list[dict]:
    groups: dict[str, list[JournalEntry]] = defaultdict(list)
    for e in session.scalars(select(JournalEntry).where(JournalEntry.incident_type == "FLAT",
                                                        JournalEntry.voided_at.is_(None))
                             .order_by(JournalEntry.id)):
        groups[e.incident_group or e.uuid].append(e)
    bikes = dict(session.execute(select(Bike.id, Bike.name).where(Bike.deleted_at.is_(None))).all())
    out = []
    for group, entries in groups.items():
        first = entries[0]
        ride = session.get(Ride, first.ride_id) if first.ride_id else None
        bike_of = ride.bike_id if ride else first.bike_id
        if bike_of is not None and bike_of not in bikes:
            continue                       # a bike deleted for good (DECISIONS 128)
        day = ride.ride_date if ride else first.entry_on
        mounted: dict[str, dict[str, Component]] = defaultdict(dict)   # wheel → TIRE / INNER_TUBE that day
        # what this flat's fix put in (the same day) was not the punctured tube or tire
        fix_sessions = {e.repair_session_id for e in entries if e.repair_session_id}
        put_in_by_fix = set(session.scalars(select(Installation.component_id).where(
            Installation.install_session_id.in_(fix_sessions)))) if fix_sessions else set()
        if ride is not None:
            for p in parts_on_ride(session, ride):
                if p["component_id"] in put_in_by_fix:
                    continue
                if p["component_type"] in ("TIRE", "INNER_TUBE"):
                    w = _wheel_of(session, p["component_id"], day)
                    if w:
                        mounted[w].setdefault(p["component_type"], session.get(Component, p["component_id"]))
        wheels: dict[str | None, dict] = {}
        for e in entries:
            comp = session.get(Component, e.component_id) if e.component_id else None
            if comp is not None:
                w, kind = _wheel_of(session, comp.id, day), comp.component_type
            else:
                w = _wheel_from_text(e.affected)
                kind = "INNER_TUBE" if "tube" in (e.affected or "").lower() else "TIRE"
            row = wheels.setdefault(w, {"tube": None, "tire": None, "tube_hit": False, "tire_hit": False,
                                        "repairs": [], "put_in": None, "fixed_on": None})
            if kind == "INNER_TUBE":
                row["tube_hit"], row["tube"] = True, comp or row["tube"]
            elif kind == "TIRE":
                row["tire_hit"], row["tire"] = True, comp or row["tire"]
            if e.repair:
                row["repairs"].append(e.repair_text or e.repair.lower())
                row["fixed_on"] = row["fixed_on"] or e.repaired_on
            if e.repair == "REPLACED" and kind == "INNER_TUBE" and comp is None and e.repair_session_id:
                row["put_in"] = _stock_tube_in(session, e.repair_session_id, w)
        bike_id = ride.bike_id if ride else first.bike_id
        for w, r in wheels.items():
            tube = r["tube"] or mounted.get(w, {}).get("INNER_TUBE")
            tire = r["tire"] or mounted.get(w, {}).get("TIRE")
            out.append({
                "group": group, "on": day, "ride_id": ride.id if ride else None,
                "ride": journal._ride_label(ride), "bike_id": bike_id, "bike": bikes.get(bike_id),
                "wheel": WHEEL_NAME.get(w, "Unknown wheel"),
                "damage": "Tube and tire" if r["tube_hit"] and r["tire_hit"] else "Tire" if r["tire_hit"]
                else "Tube",
                "tube_id": tube.id if tube else None, "tube": tube.label if tube else None,
                "tube_model": model_of(tube) if tube or r["tube_hit"] else None, "tube_inferred": False,
                "tire_id": tire.id if tire else None, "tire": tire.label if tire else None,
                "tire_model": model_of(tire),
                "conditions": ride.conditions if ride else None,
                "fixed": ", ".join(r["repairs"]) or None,
                "text": None if first.text == "Flat tire" else first.text,
                "_wheel": w, "_put_in": r["put_in"], "_fixed_on": r["fixed_on"]})
    return out


def _infer_stock_tubes(session: Session, rows: list[dict]) -> dict[str, float]:
    """A flat on a tube that is not a recorded part was the stock tube the last fix on that bike and wheel put
    in. Returns the km stock tubes did per model (fix → next flat, or → today while still in)."""
    today = today_local(settings.tz(session)).isoformat()
    km: dict[str, float] = defaultdict(float)
    last: dict[tuple, tuple[str, str]] = {}          # (bike, wheel) → (model, put in on)
    for r in sorted(rows, key=lambda x: x["on"]):
        key = (r["bike_id"], r["_wheel"])
        if r["tube_id"] is None and key in last and r["tube_model"] in (None, NOT_RECORDED):
            model, since = last.pop(key)
            r["tube_model"], r["tube_inferred"] = model, True
            km[model] += _bike_km(session, r["bike_id"], since, r["on"])
            if not r["_put_in"]:              # patched (or not fixed yet): the same tube rides on
                last[key] = (model, r["on"])
        if r["_put_in"]:
            last[key] = (r["_put_in"], r["_fixed_on"] or r["on"])
    for (bike_id, _w), (model, since) in last.items():
        km[model] += _bike_km(session, bike_id, since, today)
    return km


def punctures(session: Session) -> tuple[list[dict], dict[str, float]]:
    """One row per punctured wheel, newest first; and the km of stock tubes per model."""
    rows = _collect(session)
    stock_km = _infer_stock_tubes(session, rows)
    for r in rows:
        for k in ("_wheel", "_put_in", "_fixed_on"):
            r.pop(k)
    rows.sort(key=lambda r: r["on"], reverse=True)
    return rows, stock_km


def _by_model(session: Session, rows: list[dict], ctype: str, field: str, id_field: str,
              extra_km: dict[str, float] | None = None) -> list[dict]:
    """Per model, every tube (tire) on its own line with its own km, punctures and km per puncture
    (Dirk 2026-11-02: adding the km of different tires makes no sense). Stock tubes without a record of
    their own are one line "from stock" with the km inferred from the fixes."""
    by_part: dict[int, int] = defaultdict(int)
    loose: dict[str, int] = defaultdict(int)          # punctures on a tube / tire with no record of its own
    for r in rows:
        if r[field] is None:
            continue
        if r[id_field]:
            by_part[r[id_field]] += 1
        else:
            loose[r[field]] += 1
    models: dict[str, list[dict]] = defaultdict(list)
    for c in session.scalars(select(Component).where(Component.component_type == ctype,
                                                     Component.disposition != "VOIDED")):
        used = session.scalar(select(Installation.id).where(Installation.component_id == c.id,
                                                            Installation.voided_at.is_(None)).limit(1))
        if used is None and c.id not in by_part:
            continue
        u = component_usage(session, c)
        k, n = round(u["total_km"]), by_part.get(c.id, 0)
        models[model_of(c)].append({
            "component_id": c.id, "label": c.label, "km": k, "punctures": n,
            "km_per_puncture": round(k / n) if n and k else None,
            "in_use": inv.open_installation(session, c.id) is not None})
    for m, n in loose.items():
        k = round((extra_km or {}).get(m, 0)) or None
        models[m].append({"component_id": None, "label": "From stock (no record of its own)" if m != NOT_RECORDED
                          else "Not recorded", "km": k, "punctures": n,
                          "km_per_puncture": round(k / n) if n and k else None, "in_use": False})
    for m, k in (extra_km or {}).items():             # a stock tube that is still in and has not flatted
        if m not in loose and round(k):
            models[m].append({"component_id": None, "label": "From stock (no record of its own)", "km": round(k),
                              "punctures": 0, "km_per_puncture": None, "in_use": True})
    out = []
    for m, items in models.items():
        items.sort(key=lambda x: (-x["punctures"], -(x["km"] or 0), x["label"]))
        out.append({"model": m, "punctures": sum(x["punctures"] for x in items), "items": items})
    out.sort(key=lambda x: (x["model"] == NOT_RECORDED, -x["punctures"], x["model"]))
    return out


def _count(rows: list[dict], field: str, names: dict | None = None) -> list[dict]:
    c: dict[str, int] = defaultdict(int)
    for r in rows:
        v = r[field]
        c[(names or {}).get(v, v) or "Not known"] += 1
    return [{"name": k, "punctures": v} for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]


def report(session: Session) -> dict:
    rows, stock_km = punctures(session)
    return {"total": len(rows), "rows": rows,
            "by_tube": _by_model(session, rows, "INNER_TUBE", "tube_model", "tube_id", stock_km),
            "by_tire": _by_model(session, rows, "TIRE", "tire_model", "tire_id"),
            "by_bike": _count(rows, "bike"), "by_wheel": _count(rows, "wheel"),
            "by_conditions": _count(rows, "conditions", {"WET": "Wet", "DRY": "Dry"}),
            "by_damage": _count(rows, "damage")}
