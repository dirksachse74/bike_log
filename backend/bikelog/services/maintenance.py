"""Maintenance events, service rules, reminder status with explanations, snoozing, chains and brakes.

Rules never reset themselves: each rule lists the actions that reset it (default: its own action).
A liquid-wax top-up therefore never postpones hot waxing, and a brake bleed never resets the
fluid-replacement interval. Statuses are computed on read from events and contributions, so they
are always consistent with the history.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import ACTIONS, COMPONENT_TYPES, action_applies
from bikelog.models import (
    Bike, Component, Consumable, Installation, MaintenanceEvent, ReminderSnooze, ServiceRule,
    UsageContribution,
)
from bikelog.services import settings, stock
from bikelog.services.stock import add_consumable, consumable_stock, consumable_txn  # noqa: F401 (API)
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import get_component, location, open_installation, set_disposition
from bikelog.services.usage import usage_since
from bikelog.timeutil import add_months, parse_when, today_local, utc_now

SEVERITY = {"OVERDUE": 0, "DUE": 1, "ATTENTION": 1, "DUE_SOON": 2, "INSUFFICIENT_INFO": 3, "SNOOZED": 4,
            "OK": 5, "DONE_THIS_CYCLE": 6, "DISABLED": 7}
RETURNS_TO_SPARE = ("REPAIRED", "OK", "RESOLVED")
SAFETY_NOTE = "Reminders follow recorded usage only. They never confirm that a part is safe."


# ---------------------------------------------------------------- events

def log_event(session: Session, *, action_code: str, at: str, component_id: int | None = None,
              bike_id: int | None = None, symptom: str | None = None, work_done: str | None = None,
              outcome: str | None = None, measurement_value: float | None = None, measurement_unit: str | None = None,
              consumable_id: int | None = None, consumable_qty: float | None = None, cost_cents: int | None = None,
              notes: str | None = None, batch_ref: str | None = None, work_session_id: int | None = None,
              disposition_after: str | None = None) -> MaintenanceEvent:
    """Record work on a part. Supplies used become a separate stock USE (no cost: the cost belongs to
    the purchase). ``cost_cents`` is an extra service cost such as a shop fee. For a part awaiting
    repair, a successful outcome returns it to the spares (or pass ``disposition_after``)."""
    action = ACTIONS.get(action_code)
    if not action:
        raise DomainError(f"Unknown maintenance action {action_code!r}")
    comp = None
    if component_id is not None:
        comp = get_component(session, component_id)
        if not action_applies(action, comp.component_type):
            raise DomainError(f"'{action.name}' does not apply to a {COMPONENT_TYPES[comp.component_type].name.lower()}")
        if bike_id is None:
            loc = location(session, comp)
            bike_id = loc.get("bike_id")
    elif bike_id is None:
        raise DomainError("Pick the component (or at least the bike) the work was done on")
    if action.outcomes and outcome and outcome not in action.outcomes:
        raise DomainError(f"Outcome must be one of {', '.join(action.outcomes)}")
    if consumable_id is not None and not session.get(Consumable, consumable_id):
        raise NotFound("Consumable not found")
    w = parse_when(at, settings.tz(session))
    ev = MaintenanceEvent(action_code=action_code, component_id=component_id, bike_id=bike_id, performed_at=w.raw,
                          performed_on=w.local_date, sort_utc=w.utc, symptom=symptom, work_done=work_done,
                          outcome=outcome, measurement_value=measurement_value, measurement_unit=measurement_unit,
                          consumable_id=consumable_id, consumable_qty=consumable_qty, cost_cents=cost_cents,
                          notes=notes, batch_ref=batch_ref, work_session_id=work_session_id)
    session.add(ev)
    session.flush()
    if consumable_id is not None:
        stock.use(session, consumable_id, qty=consumable_qty, on=w.local_date, work_session_id=work_session_id,
                  maintenance_event_id=ev.id)
    if comp is not None:
        _clear_obsolete_snoozes(session, comp, action_code)
        after = disposition_after
        if after is None and comp.disposition == "AWAITING_SERVICE" and outcome in RETURNS_TO_SPARE \
                and not open_installation(session, comp.id):
            after = "STORED"
        if after is not None:
            set_disposition(session, comp.id, after, on=w.raw, note=f"after {action.name.lower()}",
                            work_session_id=work_session_id)
    session.flush()
    return ev


def log_batch(session: Session, *, action_code: str, at: str, component_ids: list[int], **common) -> list[MaintenanceEvent]:
    """Same action on several parts at once (e.g. lube every installed chain)."""
    if not component_ids:
        raise DomainError("Pick at least one component")
    ref = str(uuid.uuid4())
    return [log_event(session, action_code=action_code, at=at, component_id=cid, batch_ref=ref, **common)
            for cid in component_ids]


def void_event(session: Session, event_id: int, reason: str) -> MaintenanceEvent:
    ev = session.get(MaintenanceEvent, event_id)
    if not ev:
        raise NotFound("Maintenance event not found")
    if not reason:
        raise DomainError("Say why this entry is wrong")
    if not ev.voided_at:
        ev.voided_at, ev.void_reason = utc_now(), reason
        session.flush()
    return ev


def _clear_obsolete_snoozes(session: Session, comp: Component, action_code: str) -> None:
    codes = set()
    for rule in effective_rules(session, comp):
        if action_code in _reset_actions(rule) or rule.cycle_action_code == action_code:
            codes.add(rule.rule_code)
    if not codes:
        return
    for s in session.scalars(select(ReminderSnooze).where(
            ReminderSnooze.component_id == comp.id, ReminderSnooze.rule_code.in_(codes),
            ReminderSnooze.cleared_at.is_(None))):
        s.cleared_at = utc_now()


def events_for(session: Session, *, component_id: int | None = None, bike_id: int | None = None,
               limit: int = 200) -> list[dict]:
    q = select(MaintenanceEvent)
    if component_id is not None:
        q = q.where(MaintenanceEvent.component_id == component_id)
    if bike_id is not None:
        q = q.where(MaintenanceEvent.bike_id == bike_id)
    q = q.order_by(MaintenanceEvent.sort_utc.desc(), MaintenanceEvent.id.desc()).limit(limit)
    labels = dict(session.execute(select(Component.id, Component.label)).all())
    bikes = dict(session.execute(select(Bike.id, Bike.name)).all())
    consumables = dict(session.execute(select(Consumable.id, Consumable.name)).all())
    out = []
    for e in session.scalars(q):
        a = ACTIONS.get(e.action_code)
        out.append({"id": e.id, "action_code": e.action_code, "action": a.name if a else e.action_code,
                    "component_id": e.component_id, "component": labels.get(e.component_id),
                    "bike_id": e.bike_id, "bike": bikes.get(e.bike_id), "performed_at": e.performed_at,
                    "performed_on": e.performed_on, "date_only": len(e.performed_at) == 10, "symptom": e.symptom,
                    "work_done": e.work_done, "outcome": e.outcome, "measurement_value": e.measurement_value,
                    "measurement_unit": e.measurement_unit, "consumable": consumables.get(e.consumable_id),
                    "consumable_qty": e.consumable_qty, "cost_cents": e.cost_cents, "notes": e.notes,
                    "voided": bool(e.voided_at), "void_reason": e.void_reason, "batch_ref": e.batch_ref})
    return out


# ---------------------------------------------------------------- rules

def _reset_actions(rule: ServiceRule) -> list[str]:
    acts = json.loads(rule.reset_actions_json or "[]")
    return acts or [rule.action_code]


def effective_rules(session: Session, comp: Component, include_disabled: bool = False) -> list[ServiceRule]:
    by_code: dict[str, ServiceRule] = {}
    for r in session.scalars(select(ServiceRule).where(ServiceRule.component_type == comp.component_type)):
        by_code[r.rule_code] = r
    for r in session.scalars(select(ServiceRule).where(ServiceRule.component_id == comp.id)):
        by_code[r.rule_code] = r  # component rule replaces the type default
    rules = sorted(by_code.values(), key=lambda r: r.rule_code)
    return rules if include_disabled else [r for r in rules if r.active]


RULE_FIELDS = ("name", "interval_km", "interval_months", "window_min_km", "window_max_km", "warn_km", "warn_days",
               "active", "origin", "notes")


def _validate_rule(r: ServiceRule) -> None:
    if r.trigger == "INTERVAL" and r.interval_km is None and r.interval_months is None:
        raise DomainError("A rule needs a distance interval, a calendar interval, or both")
    if r.trigger == "CYCLE_WINDOW":
        if r.window_min_km is None or r.window_max_km is None or r.window_max_km < r.window_min_km:
            raise DomainError("The window needs a start and an end (end ≥ start)")
    for v in (r.interval_km, r.window_min_km, r.window_max_km):
        if v is not None and v <= 0:
            raise DomainError("Intervals must be positive")
    if r.interval_months is not None and r.interval_months <= 0:
        raise DomainError("Intervals must be positive")


def update_rule(session: Session, rule_id: int, **fields) -> ServiceRule:
    rule = session.get(ServiceRule, rule_id)
    if not rule:
        raise NotFound("Rule not found")
    for k, v in fields.items():
        if k in RULE_FIELDS:
            setattr(rule, k, v)
    if rule.origin == "DEFAULT" and set(fields) - {"active", "origin"}:
        rule.origin = fields.get("origin") or "PERSONAL"
    _validate_rule(rule)
    session.flush()
    return rule


def set_component_rule(session: Session, component_id: int, *, rule_code: str | None = None,
                       action_code: str | None = None, **fields) -> ServiceRule:
    """Add a component-specific rule, or override a type default (same rule_code) for one part."""
    comp = get_component(session, component_id)
    existing = None
    if rule_code:
        existing = session.scalar(select(ServiceRule).where(ServiceRule.component_id == comp.id,
                                                            ServiceRule.rule_code == rule_code))
    if existing:
        return update_rule(session, existing.id, **fields)
    template = None
    if rule_code:
        template = session.scalar(select(ServiceRule).where(ServiceRule.component_type == comp.component_type,
                                                            ServiceRule.rule_code == rule_code))
    if template is None:
        if not action_code or action_code not in ACTIONS:
            raise DomainError("Choose the maintenance action this rule asks for")
        if not action_applies(ACTIONS[action_code], comp.component_type):
            raise DomainError("That action does not apply to this component")
        rule_code = rule_code or f"CUSTOM_{action_code}_{uuid.uuid4().hex[:6].upper()}"
    rule = ServiceRule(
        rule_code=rule_code, component_id=comp.id,
        name=fields.get("name") or (template.name if template else ACTIONS[action_code].name),
        action_code=template.action_code if template else action_code,
        trigger=template.trigger if template else "INTERVAL",
        interval_km=template.interval_km if template else None,
        interval_months=template.interval_months if template else None,
        window_min_km=template.window_min_km if template else None,
        window_max_km=template.window_max_km if template else None,
        cycle_action_code=template.cycle_action_code if template else None,
        reset_actions_json=template.reset_actions_json if template else json.dumps([action_code]),
        warn_km=template.warn_km if template else None, warn_days=template.warn_days if template else None,
        origin="PERSONAL", active=True)
    for k, v in fields.items():
        if k in RULE_FIELDS:
            setattr(rule, k, v)
    _validate_rule(rule)
    session.add(rule)
    session.flush()
    return rule


def rule_row(r: ServiceRule) -> dict:
    return {"id": r.id, "rule_code": r.rule_code, "name": r.name, "component_type": r.component_type,
            "component_id": r.component_id, "action_code": r.action_code,
            "action": ACTIONS[r.action_code].name if r.action_code in ACTIONS else r.action_code,
            "trigger": r.trigger, "interval_km": r.interval_km, "interval_months": r.interval_months,
            "window_min_km": r.window_min_km, "window_max_km": r.window_max_km,
            "cycle_action_code": r.cycle_action_code, "reset_actions": _reset_actions(r), "warn_km": r.warn_km,
            "warn_days": r.warn_days, "origin": r.origin, "active": r.active, "notes": r.notes}


# ---------------------------------------------------------------- status

def _last_event(session: Session, comp_id: int, actions: list[str]) -> MaintenanceEvent | None:
    return session.scalar(select(MaintenanceEvent).where(
        MaintenanceEvent.component_id == comp_id, MaintenanceEvent.action_code.in_(actions),
        MaintenanceEvent.voided_at.is_(None)).order_by(MaintenanceEvent.sort_utc.desc(), MaintenanceEvent.id.desc()))


def _tracking_start(session: Session, comp: Component) -> tuple[str | None, str | None]:
    """For a part that was NEW when tracking started: (instant, date) usage and age count from."""
    first = session.scalar(select(Installation).where(Installation.component_id == comp.id,
                                                      Installation.voided_at.is_(None))
                           .order_by(Installation.installed_utc))
    d = comp.purchase_date or (first.installed_at[:10] if first else comp.created_at[:10])
    return (None, d)


def _uncertain_since(session: Session, comp_id: int, since_utc: str | None) -> float:
    q = select(UsageContribution.km).where(UsageContribution.component_id == comp_id,
                                           UsageContribution.state == "COUNTED", UsageContribution.certain.is_(False))
    if since_utc:
        q = q.where(UsageContribution.sort_utc >= since_utc)
    return round(sum(session.scalars(q)), 3)


def _km_status(used: float, limit: float, warn: float | None) -> str:
    remaining = limit - used
    if remaining <= 0:
        return "OVERDUE" if used > limit * 1.1 else "DUE"
    if remaining <= (warn if warn is not None else 0.1 * limit):
        return "DUE_SOON"
    return "OK"


def _day_status(days_left: int, warn_days: int | None) -> str:
    if days_left < 0:
        return "OVERDUE"
    if days_left == 0:
        return "DUE"
    if days_left <= (warn_days if warn_days is not None else 30):
        return "DUE_SOON"
    return "OK"


def _worst(*statuses: str) -> str:
    return min(statuses, key=lambda s: SEVERITY[s])


def rule_status(session: Session, comp: Component, rule: ServiceRule, today: date | None = None) -> dict:
    tz = settings.tz(session)
    today = today or today_local(tz)
    act_name = ACTIONS[rule.action_code].name.lower() if rule.action_code in ACTIONS else rule.action_code
    base = {"rule_id": rule.id, "rule_code": rule.rule_code, "name": rule.name, "action_code": rule.action_code,
            "component_id": comp.id, "component": comp.label, "component_type": comp.component_type,
            "origin": rule.origin, "trigger": rule.trigger}
    if not rule.active:
        return {**base, "status": "DISABLED", "explanation": "Rule disabled for this part."}
    if rule.trigger == "CYCLE_WINDOW":
        res = _cycle_status(session, comp, rule, act_name)
    else:
        res = _interval_status(session, comp, rule, act_name, today)
    res = {**base, **res}
    _apply_snooze(session, comp, rule, res, today)
    return res


def _interval_status(session: Session, comp: Component, rule: ServiceRule, act_name: str, today: date) -> dict:
    last = _last_event(session, comp.id, _reset_actions(rule))
    if last:
        since_utc, since_date = last.sort_utc, date.fromisoformat(last.performed_on)
        basis = f"last {act_name} on {last.performed_on}"
    elif comp.prior_usage == "NEW":
        since_utc, d = _tracking_start(session, comp)
        since_date = date.fromisoformat(d)
        basis = f"new part, no {act_name} recorded yet"
    else:
        lifetime = usage_since(session, comp.id, None)
        return {"status": "INSUFFICIENT_INFO", "used_km": None, "last_done": None,
                "explanation": f"Insufficient information: no {act_name} recorded for {comp.label} and its earlier "
                               f"history is unknown ({lifetime:,.0f} km tracked so far). Log the last {act_name} "
                               "(a date is enough) to start this reminder."}
    parts, statuses = [], []
    out: dict = {"last_done": last.performed_on if last else None, "since": basis}
    if rule.interval_km is not None:
        used = usage_since(session, comp.id, since_utc)
        unc = _uncertain_since(session, comp.id, since_utc)
        st = _km_status(used, rule.interval_km, rule.warn_km)
        statuses.append(st)
        remaining = rule.interval_km - used
        txt = f"{used:,.0f} km since {basis} (interval {rule.interval_km:,.0f} km): "
        if remaining > 0:
            txt += f"{remaining:,.0f} km left"
        elif remaining < 0:
            txt += f"due at {rule.interval_km:,.0f} km, {-remaining:,.0f} km over"
        else:
            txt += f"due now at {rule.interval_km:,.0f} km"
        if unc:
            txt += f" (includes {unc:,.0f} km with uncertain assignment)"
        parts.append(txt)
        out.update(used_km=used, interval_km=rule.interval_km, remaining_km=round(remaining, 3), uncertain_km=unc)
    if rule.interval_months is not None:
        due = add_months(since_date, rule.interval_months)
        days_left = (due - today).days
        st = _day_status(days_left, rule.warn_days)
        statuses.append(st)
        when = since_date.isoformat()
        txt = (f"{'last ' + act_name if last else 'in use since'} {when}, interval {rule.interval_months} months: "
               f"due {due.isoformat()}")
        txt += f" ({days_left} days left)" if days_left > 0 else (" (today)" if days_left == 0 else
                                                                  f" ({-days_left} days overdue)")
        parts.append(txt)
        out.update(due_date=due.isoformat(), days_left=days_left, interval_months=rule.interval_months)
    # actions that look related but do not reset this rule (e.g. a bleed vs. full fluid replacement)
    if rule.action_code == "BRAKE_FLUID_REPLACE":
        bleed = _last_event(session, comp.id, ["BRAKE_BLEED"])
        if bleed and (not last or bleed.sort_utc >= last.sort_utc):
            parts.append(f"bleed on {bleed.performed_on} does not reset the fluid-replacement interval")
    out["status"] = _worst(*statuses)
    out["explanation"] = "; ".join(parts) + "."
    return out


def _cycle_status(session: Session, comp: Component, rule: ServiceRule, act_name: str) -> dict:
    cycle_act = ACTIONS[rule.cycle_action_code].name.lower() if rule.cycle_action_code in ACTIONS else rule.cycle_action_code
    start = _last_event(session, comp.id, [rule.cycle_action_code])
    lo, hi = rule.window_min_km, rule.window_max_km
    window = f"{lo:,.0f}–{hi:,.0f} km after {cycle_act}"
    if not start:
        return {"status": "INSUFFICIENT_INFO", "used_km": None,
                "explanation": f"Insufficient information: no {cycle_act} recorded for {comp.label}, so the "
                               f"{act_name} window ({window}) cannot be placed."}
    used = usage_since(session, comp.id, start.sort_utc)
    done = session.scalar(select(MaintenanceEvent).where(
        MaintenanceEvent.component_id == comp.id, MaintenanceEvent.action_code.in_(_reset_actions(rule)),
        MaintenanceEvent.voided_at.is_(None),
        (MaintenanceEvent.sort_utc > start.sort_utc)
        | ((MaintenanceEvent.sort_utc == start.sort_utc) & (MaintenanceEvent.id > start.id)))
        .order_by(MaintenanceEvent.sort_utc))
    out = {"used_km": used, "window_min_km": lo, "window_max_km": hi, "cycle_started": start.performed_on,
           "last_done": done.performed_on if done else None}
    if done:
        at_km = usage_since(session, comp.id, start.sort_utc) - usage_since(session, comp.id, done.sort_utc)
        out["status"] = "DONE_THIS_CYCLE"
        out["explanation"] = (f"{act_name.capitalize()} done on {done.performed_on} (about {at_km:,.0f} km into the "
                              f"cycle that began with {cycle_act} on {start.performed_on}). Next one in the next cycle.")
        return out
    head = f"{used:,.0f} km since {cycle_act} on {start.performed_on}; one {act_name} is due {window}"
    warn = rule.warn_km if rule.warn_km is not None else 0
    if used > hi:
        out["status"], tail = "OVERDUE", f": window passed by {used - hi:,.0f} km"
    elif used >= lo:
        out["status"], tail = "DUE", ": window is open"
    elif used >= lo - warn:
        out["status"], tail = "DUE_SOON", f": window opens in {lo - used:,.0f} km"
    else:
        out["status"], tail = "OK", f": window opens in {lo - used:,.0f} km"
    out["explanation"] = head + tail + f". It does not postpone the next {cycle_act}."
    return out


def _apply_snooze(session: Session, comp: Component, rule: ServiceRule, res: dict, today: date) -> None:
    snooze = session.scalar(select(ReminderSnooze).where(
        ReminderSnooze.component_id == comp.id, ReminderSnooze.rule_code == rule.rule_code,
        ReminderSnooze.cleared_at.is_(None)).order_by(ReminderSnooze.id.desc()))
    if not snooze or res["status"] not in ("DUE_SOON", "DUE", "OVERDUE"):
        return
    active_date = snooze.until_date is None or today < date.fromisoformat(snooze.until_date)
    used = res.get("used_km")
    active_km = snooze.until_km is None or (used is not None and used < snooze.until_km)
    if active_date and active_km:
        until = " and ".join(x for x in (f"until {snooze.until_date}" if snooze.until_date else "",
                                         f"until {snooze.until_km:,.0f} km" if snooze.until_km else "") if x)
        res["underlying_status"] = res["status"]
        res["status"] = "SNOOZED"
        res["snooze_id"] = snooze.id
        res["explanation"] = f"Snoozed {until} (no maintenance recorded). " + res["explanation"]


def snooze(session: Session, component_id: int, rule_code: str, *, until_date: str | None = None,
           extra_km: float | None = None, note: str | None = None) -> ReminderSnooze:
    comp = get_component(session, component_id)
    rule = next((r for r in effective_rules(session, comp) if r.rule_code == rule_code), None)
    if not rule:
        raise NotFound("No such reminder for this component")
    if not until_date and not extra_km:
        raise DomainError("Snooze until a date or for some kilometres")
    until_km = None
    if extra_km:
        st = rule_status(session, comp, rule)
        until_km = (st.get("used_km") or 0) + extra_km
    for old in session.scalars(select(ReminderSnooze).where(
            ReminderSnooze.component_id == comp.id, ReminderSnooze.rule_code == rule_code,
            ReminderSnooze.cleared_at.is_(None))):
        old.cleared_at = utc_now()
    s = ReminderSnooze(component_id=comp.id, rule_code=rule_code, until_date=until_date, until_km=until_km, note=note)
    session.add(s)
    session.flush()
    return s


def unsnooze(session: Session, snooze_id: int) -> None:
    s = session.get(ReminderSnooze, snooze_id)
    if s and not s.cleared_at:
        s.cleared_at = utc_now()
        session.flush()


def attention_items(session: Session, comp: Component) -> list[dict]:
    """Condition-based attention: the latest finding of an inspection/measurement says something is off."""
    out = []
    for code, action in ACTIONS.items():
        if not action.attention_outcomes or not action_applies(action, comp.component_type):
            continue
        last = _last_event(session, comp.id, [code])
        if last and last.outcome in action.attention_outcomes:
            meas = f" ({last.measurement_value:g} {last.measurement_unit or ''})".rstrip() if last.measurement_value is not None else ""
            out.append({"rule_code": f"ATTENTION_{code}", "name": action.name, "action_code": code,
                        "component_id": comp.id, "component": comp.label, "component_type": comp.component_type,
                        "status": "ATTENTION", "event_id": last.id,
                        "explanation": f"{action.name} on {last.performed_on}: {last.outcome.replace('_', ' ').lower()}"
                                       f"{meas}{' — ' + last.symptom if last.symptom else ''}. Stays until a newer "
                                       f"{action.name.lower()} records a different result."})
    return out


def component_status(session: Session, comp: Component, today: date | None = None) -> list[dict]:
    rows = [rule_status(session, comp, r, today) for r in effective_rules(session, comp, include_disabled=True)]
    rows += attention_items(session, comp)
    return sorted(rows, key=lambda r: SEVERITY[r["status"]])


def queue(session: Session, *, bike_id: int | None = None, include_ok: bool = False,
          today: date | None = None) -> list[dict]:
    """What needs attention next and why, for installed parts."""
    out = []
    for comp in session.scalars(select(Component).where(Component.status == "ACTIVE").order_by(Component.label)):
        loc = location(session, comp)
        if loc["state"] != "INSTALLED" or (bike_id is not None and loc.get("bike_id") != bike_id):
            continue
        for row in component_status(session, comp, today):
            if row["status"] in ("DISABLED", "DONE_THIS_CYCLE") or (row["status"] == "OK" and not include_ok):
                continue
            out.append({**row, "bike_id": loc.get("bike_id"), "bike": loc.get("bike"), "slot": loc.get("slot")})
    return sorted(out, key=lambda r: (SEVERITY[r["status"]], r.get("bike") or "", r["component"]))


# ---------------------------------------------------------------- chains & brakes

def chain_overview(session: Session) -> list[dict]:
    out = []
    for comp in session.scalars(select(Component).where(Component.component_type == "CHAIN")
                                .order_by(Component.label)):
        loc = location(session, comp)
        lifetime = usage_since(session, comp.id, None)
        hot = _last_event(session, comp.id, ["WAX_HOT"])
        since_hot = usage_since(session, comp.id, hot.sort_utc) if hot else None
        wear = _last_event(session, comp.id, ["CHAIN_MEASURE_WEAR"])
        worn = bool(wear and wear.outcome == "AT_LIMIT")
        if comp.status == "RETIRED":
            state, text = "RETIRED", loc["text"]
        elif loc["state"] == "INSTALLED":
            state, text = "INSTALLED", f"On {loc['text']}"
        elif worn:
            state, text = "WORN", f"Wear at limit on {wear.performed_on}; do not install"
        elif comp.disposition == "AWAITING_SERVICE":
            state, text = "AWAITING_SERVICE", "Awaiting preparation or repair"
        elif hot and since_hot == 0:
            state, text = "READY_TO_INSTALL", f"Hot waxed on {hot.performed_on}, 0 km since"
        elif hot:
            state, text = "NEEDS_HOT_WAX", f"{since_hot:,.0f} km since hot wax on {hot.performed_on}"
        elif comp.prior_usage == "NEW":
            state, text = "NEW_UNWAXED", "New chain, not hot waxed yet (factory grease)"
        else:
            state, text = "UNKNOWN", "No hot wax recorded"
        out.append({"component_id": comp.id, "label": comp.label, "state": state, "text": text,
                    "lifetime_km": lifetime, "km_since_hot_wax": since_hot,
                    "last_hot_wax": hot.performed_on if hot else None,
                    "last_wear": {"date": wear.performed_on, "value": wear.measurement_value,
                                  "unit": wear.measurement_unit, "outcome": wear.outcome} if wear else None,
                    "location": loc})
    return out


def brake_overview(session: Session, bike_id: int | None = None) -> list[dict]:
    out = []
    for comp in session.scalars(select(Component).where(Component.component_type == "BRAKE_CIRCUIT",
                                                        Component.status == "ACTIVE").order_by(Component.label)):
        loc = location(session, comp)
        if bike_id is not None and loc.get("bike_id") != bike_id:
            continue
        rule = next((r for r in effective_rules(session, comp) if r.action_code == "BRAKE_FLUID_REPLACE"), None)
        fluid = rule_status(session, comp, rule) if rule else None
        bleed = _last_event(session, comp.id, ["BRAKE_BLEED"])
        out.append({"component_id": comp.id, "label": comp.label, "location": loc,
                    "position": (loc.get("slot") or "").replace("_BRAKE", "").title() or None,
                    "fluid": fluid,
                    "last_bleed": {"date": bleed.performed_on, "symptom": bleed.symptom, "work_done": bleed.work_done,
                                   "outcome": bleed.outcome} if bleed else None})
    return out


def installed_parts_for_action(session: Session, bike_id: int, action_code: str) -> list[dict]:
    """Preselection for quick logging: installed parts on a bike that the action applies to."""
    action = ACTIONS.get(action_code)
    if not action:
        raise DomainError("Unknown action")
    out = []
    from bikelog.services.inventory import bike_setup, get_bike
    for row in bike_setup(session, get_bike(session, bike_id)):
        if action_applies(action, row["component_type"]):
            out.append(row)
    return out
