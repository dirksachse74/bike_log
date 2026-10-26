"""Maintenance events, service rules, reminder status with explanations, snoozing, chains and brakes.

Rules never reset themselves: each rule lists the actions that reset it (default: its own action).
A liquid-wax top-up therefore never postpones hot waxing, and a brake bleed never resets the
fluid-replacement interval. Statuses are computed on read from events and contributions, so they
are always consistent with the history.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.catalog import (
    ACTIONS, BIKE, CHARGE_ACTIONS, COMPONENT_TYPES, OUT_OF_USE, SHIFTING_TYPES, TIRE_SETUPS, TORQUE_TYPES,
    action_applies, outcome_from_measurement,
)
from bikelog.models import (
    Bike, Component, Consumable, Installation, JournalEntry, MaintenanceEvent, Product, ReminderSnooze, Ride,
    ServiceRule, UsageAdjustment, UsageContribution,
)
from bikelog.services import settings, stock
from bikelog.services.stock import add_consumable, consumable_stock, consumable_txn  # noqa: F401 (API)
from bikelog.services.errors import DomainError, NotFound
from bikelog.services.inventory import (
    get_bike, get_component, location, open_installation, set_disposition, shifting_of, tire_setup_of,
)
from bikelog.services.usage import bike_hours_since, bike_km_since, hours_since, usage_since
from bikelog.timeutil import add_months, parse_when, today_local, utc_now

SEVERITY = {"OVERDUE": 0, "DUE": 1, "ATTENTION": 1, "DUE_SOON": 2, "INSUFFICIENT_INFO": 3, "SNOOZED": 4,
            "OK": 5, "DONE_THIS_CYCLE": 6, "DISABLED": 7, "NOT_APPLICABLE": 8}
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
    else:
        get_bike(session, bike_id)
        if not action_applies(action, BIKE):
            raise DomainError(f"'{action.name}' is done on a part: pick the part")
    if measurement_value is not None and action.unit and not measurement_unit:
        measurement_unit = action.unit
    if not outcome:   # a measurement sets the outcome from the limits (e.g. pads at 0.8 mm: LOW)
        outcome = outcome_from_measurement(action, measurement_value, measurement_unit)
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
    if comp is None:
        _clear_obsolete_bike_snoozes(session, get_bike(session, bike_id), action_code)
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
    """Same action on several parts at once (e.g. lube every installed chain). A cost is one fee for the
    whole visit, so it is recorded on the first entry only (never once per part)."""
    if not component_ids:
        raise DomainError("Pick at least one component")
    ref = str(uuid.uuid4())
    cost = common.pop("cost_cents", None)
    return [log_event(session, action_code=action_code, at=at, component_id=cid, batch_ref=ref,
                      cost_cents=cost if i == 0 else None, **common)
            for i, cid in enumerate(component_ids)]


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


def _clear_obsolete_bike_snoozes(session: Session, bike: Bike, action_code: str) -> None:
    codes = {r.rule_code for r in effective_bike_rules(session, bike) if action_code in _reset_actions(r)}
    if not codes:
        return
    for s in session.scalars(select(ReminderSnooze).where(
            ReminderSnooze.bike_id == bike.id, ReminderSnooze.rule_code.in_(codes),
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


def effective_bike_rules(session: Session, bike: Bike, include_disabled: bool = False) -> list[ServiceRule]:
    """Bike-level rules (torque check, Di2 check): type defaults for "BIKE", replaced per bike."""
    by_code: dict[str, ServiceRule] = {}
    for r in session.scalars(select(ServiceRule).where(ServiceRule.component_type == BIKE)):
        by_code[r.rule_code] = r
    for r in session.scalars(select(ServiceRule).where(ServiceRule.bike_id == bike.id)):
        by_code[r.rule_code] = r
    rules = sorted(by_code.values(), key=lambda r: r.rule_code)
    return rules if include_disabled else [r for r in rules if r.active]


RULE_FIELDS = ("name", "interval_km", "interval_months", "window_min_km", "window_max_km", "warn_km", "warn_days",
               "active", "origin", "notes", "interval_hours", "warn_hours", "interval_count")


def _validate_rule(r: ServiceRule) -> None:
    if r.trigger == "INTERVAL" and r.interval_km is None and r.interval_months is None and r.interval_hours is None:
        raise DomainError("A rule needs a distance, ride-time or calendar interval (or several)")
    if r.trigger == "PARENT_COUNT" and (r.interval_count is None or r.interval_count < 1):
        raise DomainError("Give the number (at least 1), e.g. replace the quick link after 2 chains")
    if r.interval_hours is not None and r.interval_hours <= 0:
        raise DomainError("Intervals must be positive")
    if r.trigger == "ONCE_AFTER_INSTALL" and r.window_max_km is not None and r.window_max_km <= 0:
        raise DomainError("Intervals must be positive")
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
        requires_setup=template.requires_setup if template else None,
        interval_hours=template.interval_hours if template else None,
        warn_hours=template.warn_hours if template else None,
        interval_count=template.interval_count if template else None,
        notes=template.notes if template else None, origin="PERSONAL", active=True)
    for k, v in fields.items():
        if k in RULE_FIELDS:
            setattr(rule, k, v)
    _validate_rule(rule)
    session.add(rule)
    session.flush()
    return rule


def set_bike_rule(session: Session, bike_id: int, rule_code: str, **fields) -> ServiceRule:
    """Change a bike-level rule for one bike (e.g. switch the Di2 check off, torque check every 6 months)."""
    bike = get_bike(session, bike_id)
    existing = session.scalar(select(ServiceRule).where(ServiceRule.bike_id == bike.id,
                                                        ServiceRule.rule_code == rule_code))
    if existing:
        return update_rule(session, existing.id, **fields)
    t = session.scalar(select(ServiceRule).where(ServiceRule.component_type == BIKE, ServiceRule.rule_code == rule_code))
    if t is None:
        raise NotFound("No such bike reminder")
    rule = ServiceRule(rule_code=rule_code, bike_id=bike.id, name=t.name, action_code=t.action_code, trigger=t.trigger,
                       interval_km=t.interval_km, interval_months=t.interval_months, interval_hours=t.interval_hours,
                       reset_actions_json=t.reset_actions_json, warn_km=t.warn_km, warn_days=t.warn_days,
                       warn_hours=t.warn_hours, requires_setup=t.requires_setup, notes=t.notes, origin="PERSONAL",
                       active=True)
    for k, v in fields.items():
        if k in RULE_FIELDS:
            setattr(rule, k, v)
    _validate_rule(rule)
    session.add(rule)
    session.flush()
    return rule


def rule_row(r: ServiceRule) -> dict:
    return {"id": r.id, "rule_code": r.rule_code, "name": r.name, "component_type": r.component_type,
            "component_id": r.component_id, "bike_id": r.bike_id, "action_code": r.action_code,
            "action": ACTIONS[r.action_code].name if r.action_code in ACTIONS else r.action_code,
            "trigger": r.trigger, "interval_km": r.interval_km, "interval_months": r.interval_months,
            "window_min_km": r.window_min_km, "window_max_km": r.window_max_km,
            "cycle_action_code": r.cycle_action_code, "reset_actions": _reset_actions(r), "warn_km": r.warn_km,
            "warn_days": r.warn_days, "origin": r.origin, "active": r.active, "notes": r.notes,
            "requires_setup": r.requires_setup, "interval_hours": r.interval_hours, "warn_hours": r.warn_hours,
            "interval_count": r.interval_count}


# ---------------------------------------------------------------- status

@dataclass
class _Subject:
    """What a rule is about: one part, or a whole bike (bike-level rules such as the torque check)."""
    session: Session
    comp: Component | None = None
    bike: Bike | None = None

    @property
    def label(self) -> str:
        return self.comp.label if self.comp else self.bike.name

    def last_event(self, actions: list[str]) -> MaintenanceEvent | None:
        if self.comp:
            return _last_event(self.session, self.comp.id, actions)
        return self.session.scalar(select(MaintenanceEvent).where(
            MaintenanceEvent.bike_id == self.bike.id, MaintenanceEvent.component_id.is_(None),
            MaintenanceEvent.action_code.in_(actions), MaintenanceEvent.voided_at.is_(None))
            .order_by(MaintenanceEvent.sort_utc.desc(), MaintenanceEvent.id.desc()))

    def km_since(self, since_utc: str | None) -> float:
        return usage_since(self.session, self.comp.id, since_utc) if self.comp else \
            bike_km_since(self.session, self.bike.id, since_utc)

    def uncertain_since(self, since_utc: str | None) -> float:
        return _uncertain_since(self.session, self.comp.id, since_utc) if self.comp else 0.0

    def hours_since(self, since_utc: str | None) -> tuple[float, int]:
        return hours_since(self.session, self.comp.id, since_utc) if self.comp else \
            bike_hours_since(self.session, self.bike.id, since_utc)


def _last_event(session: Session, comp_id: int, actions: list[str]) -> MaintenanceEvent | None:
    return session.scalar(select(MaintenanceEvent).where(
        MaintenanceEvent.component_id == comp_id, MaintenanceEvent.action_code.in_(actions),
        MaintenanceEvent.voided_at.is_(None)).order_by(MaintenanceEvent.sort_utc.desc(), MaintenanceEvent.id.desc()))


def _tracking_start(session: Session, comp: Component) -> tuple[str | None, str | None]:
    """For a part that was NEW when tracking started: (instant, date) usage and age count from."""
    first = session.scalar(select(Installation).where(Installation.component_id == comp.id,
                                                      Installation.voided_at.is_(None))
                           .order_by(Installation.installed_utc))
    # in use from the first install (UAT B4); a part never installed counts from when it was bought
    d = first.installed_at[:10] if first else (comp.purchase_date or comp.created_at[:10])
    return (None, d)


def _starting(session: Session, comp_id: int) -> UsageAdjustment | None:
    return session.scalar(select(UsageAdjustment).where(
        UsageAdjustment.component_id == comp_id, UsageAdjustment.kind == "STARTING",
        UsageAdjustment.voided_at.is_(None)).order_by(UsageAdjustment.id.desc()))


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
    why_not = _setup_mismatch(session, rule, comp=comp)
    if why_not:
        return {**base, "status": "NOT_APPLICABLE", "requires_setup": rule.requires_setup, "explanation": why_not}
    if rule.trigger == "CYCLE_WINDOW":
        res = _cycle_status(session, comp, rule, act_name)
    elif rule.trigger == "PARENT_COUNT":
        res = _parent_count_status(session, comp, rule)
    elif rule.trigger == "ONCE_AFTER_INSTALL":
        res = _once_status(session, comp, rule, act_name)
    else:
        res = _interval_status(_Subject(session, comp=comp), rule, act_name, today)
        if res["status"] not in ("INSUFFICIENT_INFO",):
            _add_wet_ride(session, comp, rule, res)
        _add_age(comp, res, today)
    res = {**base, **res}
    _apply_snooze(session, rule, res, today, component_id=comp.id)
    return res


def bike_rule_status(session: Session, bike: Bike, rule: ServiceRule, today: date | None = None) -> dict:
    """Status of a bike-level rule; the torque check also asks for a re-check after newly fitted parts."""
    today = today or today_local(settings.tz(session))
    act_name = ACTIONS[rule.action_code].name.lower() if rule.action_code in ACTIONS else rule.action_code
    base = {"rule_id": rule.id, "rule_code": rule.rule_code, "name": rule.name, "action_code": rule.action_code,
            "component_id": None, "component": None, "component_type": BIKE, "bike_id": bike.id, "bike": bike.name,
            "origin": rule.origin, "trigger": rule.trigger}
    if not rule.active:
        return {**base, "status": "DISABLED", "explanation": f"Rule switched off for {bike.name}."}
    why_not = _setup_mismatch(session, rule, bike=bike)
    if why_not:
        return {**base, "status": "NOT_APPLICABLE", "requires_setup": rule.requires_setup, "explanation": why_not}
    subj = _Subject(session, bike=bike)
    res = _interval_status(subj, rule, act_name, today)
    if rule.action_code == "TORQUE_CHECK":
        _add_torque_recheck(session, bike, subj, res)
    res = {**base, **res}
    _apply_snooze(session, rule, res, today, bike_id=bike.id)
    return res


def _setup_mismatch(session: Session, rule: ServiceRule, *, comp: Component | None = None,
                    bike: Bike | None = None) -> str | None:
    """Why a setup-dependent rule (tubeless only, mechanical shifting only, …) does not apply, or None."""
    need_code = rule.requires_setup
    if not need_code:
        return None
    if need_code in SHIFTING_TYPES:
        if bike is None:
            loc = location(session, comp)
            bike = session.get(Bike, loc["bike_id"]) if loc.get("bike_id") else None
        need = SHIFTING_TYPES[need_code].lower()
        if bike is None:
            return f"Only for {need} shifting; this part is not on a bike."
        have = shifting_of(session, bike)
        if have == need_code:
            return None
        if have is None:
            return f"Only for {need} shifting; set the shifting on {bike.name} (bike page → Edit) to use this reminder."
        return f"Only for {need} shifting; {bike.name} is set to {SHIFTING_TYPES[have].lower()}."
    setup, wheel = tire_setup_of(session, comp)
    need = TIRE_SETUPS.get(need_code, need_code).lower()
    if wheel is None:
        return f"Only for a {need} setup; it is not on a wheel."
    default_used = setup is None
    if default_used:
        setup = settings.get(session, "default_tire_setup") or None
    if setup == need_code:
        return None
    if setup is None:
        return f"Only for a {need} setup; tube or tubeless is not set on {wheel.label}; set it on the wheel to use this reminder."
    have = TIRE_SETUPS.get(setup, setup).lower()
    if default_used:
        return (f"Only for a {need} setup; {wheel.label} has no setup of its own, so the default "
                f"({have}, Settings) applies.")
    return f"Only for a {need} setup; {wheel.label} is set to {have}."


def _interval_status(subj: _Subject, rule: ServiceRule, act_name: str, today: date) -> dict:
    session, comp = subj.session, subj.comp
    last = subj.last_event(_reset_actions(rule))
    if last:
        since_utc, since_date = last.sort_utc, date.fromisoformat(last.performed_on)
        basis = f"last {act_name} on {last.performed_on}"
    elif comp is None:
        return {"status": "INSUFFICIENT_INFO", "used_km": None, "last_done": None,
                "explanation": f"Insufficient information: no '{rule.name}' recorded for {subj.label} yet. Log "
                               f"the last one (a date is enough) to start this reminder."}
    elif rule.action_code in CHARGE_ACTIONS:
        return {"status": "INSUFFICIENT_INFO", "used_km": None, "last_done": None,
                "explanation": f"Insufficient information: no charge recorded for {comp.label} yet. Tap "
                               "'Charged' after the next charge (or log the last one with its date) to start "
                               "this reminder."}
    elif comp.prior_usage == "NEW":
        since_utc, d = _tracking_start(session, comp)
        since_date = date.fromisoformat(d)
        basis = f"new part, no {act_name} recorded yet"
    else:
        lifetime = usage_since(session, comp.id, None)
        start = _starting(session, comp.id)
        if start:
            return {"status": "INSUFFICIENT_INFO", "used_km": None, "last_done": None,
                    "explanation": f"Insufficient information: no {act_name} on record; {comp.label} has "
                                   f"{'≈' if start.is_estimate else ''}{start.km:,.0f} km from before "
                                   f"{start.effective_at[:10]} and {lifetime:,.0f} km tracked since. Log the last "
                                   f"{act_name} (a date is enough) to start this reminder."}
        return {"status": "INSUFFICIENT_INFO", "used_km": None, "last_done": None,
                "explanation": f"Insufficient information: no {act_name} recorded for {comp.label} and its earlier "
                               f"history is unknown ({lifetime:,.0f} km tracked so far). Log the last {act_name} "
                               "(a date is enough) to start this reminder."}
    parts, statuses = [], []
    out: dict = {"last_done": last.performed_on if last else None, "since": basis}
    if rule.interval_km is not None:
        used = subj.km_since(since_utc)
        unc = subj.uncertain_since(since_utc)
        st = _km_status(used, rule.interval_km, rule.warn_km)
        statuses.append(st)
        remaining = rule.interval_km - used
        # done before the "km from before" date: the km between then and that date are inside the
        # starting value and not known, so the count is a lower bound
        start = _starting(session, comp.id) if comp is not None and last else None
        at_least = bool(start and since_utc < start.effective_utc)
        txt = f"{'at least ' if at_least else ''}{used:,.0f} km since {basis} (interval {rule.interval_km:,.0f} km): "
        if remaining > 0:
            txt += f"{remaining:,.0f} km left"
        elif remaining < 0:
            txt += f"due at {rule.interval_km:,.0f} km, {-remaining:,.0f} km over"
        else:
            txt += f"due now at {rule.interval_km:,.0f} km"
        if unc:
            txt += f" (includes {unc:,.0f} km with uncertain assignment)"
        if at_least:
            txt += (f"; the km between {last.performed_on} and {start.effective_at[:10]} are inside the "
                    f"{'≈' if start.is_estimate else ''}{start.km:,.0f} km from before")
        parts.append(txt)
        out.update(used_km=used, interval_km=rule.interval_km, remaining_km=round(remaining, 3), uncertain_km=unc,
                   km_at_least=at_least)
    if rule.interval_hours is not None:
        hours, no_time = subj.hours_since(since_utc)
        left = rule.interval_hours - hours
        st = _km_status(hours, rule.interval_hours, rule.warn_hours)
        statuses.append(st)
        txt = f"{hours:,.1f} h of riding since {basis} (interval {rule.interval_hours:,.0f} h): "
        txt += f"{left:,.1f} h left" if left > 0 else (f"{-left:,.1f} h over" if left < 0 else "due now")
        if no_time:
            txt += f" ({no_time} ride{'s' if no_time != 1 else ''} without a ride time not counted)"
        parts.append(txt)
        out.update(used_hours=hours, interval_hours=rule.interval_hours, remaining_hours=round(left, 2))
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
    if rule.action_code == "BRAKE_FLUID_REPLACE" and comp is not None:
        bleed = _last_event(session, comp.id, ["BRAKE_BLEED"])
        if bleed and (not last or bleed.sort_utc >= last.sort_utc):
            parts.append(f"bleed on {bleed.performed_on} does not reset the fluid-replacement interval")
    out["status"] = _worst(*statuses)
    out["explanation"] = "; ".join(parts) + "."
    out["since_utc"] = since_utc
    return out


def _add_wet_ride(session: Session, comp: Component, rule: ServiceRule, res: dict) -> None:
    """A wet ride since the last lube/wax makes a chain-lube rule due (ride conditions set per ride)."""
    action = ACTIONS.get(rule.action_code)
    if comp.component_type != "CHAIN" or not action or action.kind != "LUBRICATE":
        return
    q = select(Ride.ride_date).join(UsageContribution, UsageContribution.ride_id == Ride.id).where(
        UsageContribution.component_id == comp.id, UsageContribution.state == "COUNTED", Ride.conditions == "WET")
    if res.get("since_utc"):
        q = q.where(UsageContribution.sort_utc > res["since_utc"])
    wet = list(session.scalars(q.order_by(Ride.sort_utc)))
    if not wet:
        return
    res["status"] = _worst(res["status"], "DUE")
    n = len(wet)
    res["wet_rides"] = n
    res["explanation"] += (f" {n} wet ride{'s' if n != 1 else ''} since then (last {wet[-1]}): "
                           f"{action.name.lower()} after riding in the wet.")


def _add_age(comp: Component, res: dict, today: date) -> None:
    """Tires and bar tape age with time: show how old the part is when its purchase date is known."""
    if comp.component_type not in ("TIRE", "BAR_TAPE") or not comp.purchase_date:
        return
    months = (today.year - int(comp.purchase_date[:4])) * 12 + today.month - int(comp.purchase_date[5:7])
    res["age_months"] = months
    res["explanation"] += f" Bought {comp.purchase_date} ({months} month{'s' if months != 1 else ''} ago)."


def _torque_spec(session: Session, comp: Component) -> str | None:
    p = session.get(Product, comp.product_id) if comp.product_id else None
    if not p or not p.specs_json:
        return None
    v = json.loads(p.specs_json).get("torque_nm")
    return f"{v} Nm" if v not in (None, "") else None


def _add_torque_recheck(session: Session, bike: Bike, subj: _Subject, res: dict) -> None:
    """Parts fitted after the last torque check that have been ridden since: re-check them once."""
    from bikelog.services.inventory import bike_setup
    last = subj.last_event(["TORQUE_CHECK"])
    rows = [r for r in bike_setup(session, bike) if r["component_type"] in TORQUE_TYPES]
    recheck, specs = [], []
    for r in rows:
        comp = session.get(Component, r["component_id"])
        spec = _torque_spec(session, comp)
        if spec:
            specs.append(f"{comp.label} {spec}")
        inst = session.get(Installation, r["installation_id"])
        # without any torque check logged the reminder already asks for one; nothing extra to list
        if last and inst.installed_utc > last.sort_utc and usage_since(session, comp.id, inst.installed_utc) > 0:
            recheck.append(comp.label)
    if recheck:
        names = ", ".join(recheck[:6]) + (f" and {len(recheck) - 6} more" if len(recheck) > 6 else "")
        res["status"] = _worst(res["status"], "DUE")
        res["recheck"] = recheck
        res["explanation"] += f" Re-check after the first ride on newly fitted parts: {names}."
    if specs:
        res["torque_specs"] = specs
        res["explanation"] += " Torque: " + "; ".join(specs) + "."


def _once_status(session: Session, comp: Component, rule: ServiceRule, act_name: str) -> dict:
    """Once after fitting (e.g. bed in new pads): due from fitting until done, or until it has run
    window_max_km without it (then it is taken as done)."""
    inst = open_installation(session, comp.id)
    if inst is None:
        return {"status": "OK", "last_done": None, "explanation": f"Asked for once after {comp.label} is fitted."}
    done = session.scalar(select(MaintenanceEvent).where(
        MaintenanceEvent.component_id == comp.id, MaintenanceEvent.action_code.in_(_reset_actions(rule)),
        MaintenanceEvent.voided_at.is_(None), MaintenanceEvent.sort_utc >= inst.installed_utc)
        .order_by(MaintenanceEvent.sort_utc.desc()))
    used = usage_since(session, comp.id, inst.installed_utc)
    out = {"used_km": used, "last_done": done.performed_on if done else None, "since": inst.installed_at}
    if done:
        out.update(status="DONE_THIS_CYCLE", explanation=f"{act_name.capitalize()} done on {done.performed_on} "
                                                          f"after fitting on {inst.installed_at[:10]}.")
    elif rule.window_max_km is not None and used > rule.window_max_km:
        out.update(status="DONE_THIS_CYCLE",
                   explanation=f"Fitted on {inst.installed_at[:10]}, {used:,.0f} km since: taken as done "
                               f"(asked for up to {rule.window_max_km:,.0f} km after fitting).")
    else:
        out.update(status="DUE", explanation=f"Fitted on {inst.installed_at[:10]} ({used:,.0f} km since): "
                                             f"{act_name} once before riding hard. " + (rule.notes or ""))
    return out


def parents_served(session: Session, comp: Component) -> list[Component]:
    """The parent parts this part has been mounted on, oldest first (e.g. the chains a quick link was on)."""
    seen: dict[int, Component] = {}
    for i in session.scalars(select(Installation).where(
            Installation.component_id == comp.id, Installation.voided_at.is_(None),
            Installation.parent_component_id.is_not(None)).order_by(Installation.installed_utc)):
        if i.parent_component_id not in seen:
            seen[i.parent_component_id] = session.get(Component, i.parent_component_id)
    return list(seen.values())


def _parent_count_status(session: Session, comp: Component, rule: ServiceRule) -> dict:
    parents = parents_served(session, comp)
    n, limit = len(parents), rule.interval_count or 1
    kind = (COMPONENT_TYPES[comp.component_type].parent_types or ("part",))[0].replace("_", " ").lower()
    names = ", ".join(p.label for p in parents) or "none yet"
    out = {"used_count": n, "interval_count": limit, "last_done": None}
    if n > limit:
        out["status"] = "OVERDUE"
        tail = f"replace it (limit {limit})"
    elif n == limit:
        out["status"] = "DUE_SOON"
        tail = f"replace it at the next {kind} change instead of moving it on (limit {limit})"
    else:
        out["status"] = "OK"
        tail = f"can move on to {limit - n} more {kind}{'s' if limit - n != 1 else ''}"
    out["explanation"] = (f"Has been on {n} {kind}{'s' if n != 1 else ''} ({names}): {tail}. "
                          + (rule.notes or ""))
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


def _apply_snooze(session: Session, rule: ServiceRule, res: dict, today: date, *, component_id: int | None = None,
                  bike_id: int | None = None) -> None:
    who = ReminderSnooze.component_id == component_id if component_id is not None else \
        (ReminderSnooze.bike_id == bike_id) & ReminderSnooze.component_id.is_(None)
    snooze = session.scalar(select(ReminderSnooze).where(
        who, ReminderSnooze.rule_code == rule.rule_code,
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


def snooze(session: Session, component_id: int | None, rule_code: str, *, until_date: str | None = None,
           extra_km: float | None = None, note: str | None = None, bike_id: int | None = None) -> ReminderSnooze:
    """Snooze a part's reminder, or (component_id None, bike_id set) a bike-level reminder."""
    if component_id is not None:
        comp = get_component(session, component_id)
        rule = next((r for r in effective_rules(session, comp) if r.rule_code == rule_code), None)
        bike = None
    elif bike_id is not None:
        comp, bike = None, get_bike(session, bike_id)
        rule = next((r for r in effective_bike_rules(session, bike) if r.rule_code == rule_code), None)
    else:
        raise DomainError("Pick the part or the bike")
    if not rule:
        raise NotFound("No such reminder for this component")
    if not until_date and not extra_km:
        raise DomainError("Snooze until a date or for some kilometres")
    until_km = None
    if extra_km:
        st = rule_status(session, comp, rule) if comp else bike_rule_status(session, bike, rule)
        until_km = (st.get("used_km") or 0) + extra_km
    who = ReminderSnooze.component_id == comp.id if comp else \
        (ReminderSnooze.bike_id == bike.id) & ReminderSnooze.component_id.is_(None)
    for old in session.scalars(select(ReminderSnooze).where(
            who, ReminderSnooze.rule_code == rule_code, ReminderSnooze.cleared_at.is_(None))):
        old.cleared_at = utc_now()
    s = ReminderSnooze(component_id=comp.id if comp else None, bike_id=None if comp else bike.id, rule_code=rule_code,
                       until_date=until_date, until_km=until_km, note=note)
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


def _last_crash(session: Session, bike_id: int | None, after_utc: str | None = None) -> JournalEntry | None:
    if bike_id is None:
        return None
    q = select(JournalEntry).where(JournalEntry.bike_id == bike_id, JournalEntry.incident_type == "CRASH",
                                   JournalEntry.voided_at.is_(None))
    if after_utc:
        q = q.where(JournalEntry.entry_on >= after_utc[:10])
    return session.scalar(q.order_by(JournalEntry.entry_on.desc(), JournalEntry.id.desc()))


def spoke_info(session: Session, wheel: Component) -> dict:
    """A wheel's spokes: the spoke set on it (type, count, lengths; values from the product are marked as
    such) and the broken spokes replaced since it was laced (a re-lace or a new spoke set resets the count)."""
    spokes = None
    for i in session.scalars(select(Installation).where(Installation.parent_component_id == wheel.id,
                                                        Installation.removed_utc.is_(None),
                                                        Installation.voided_at.is_(None))):
        c = session.get(Component, i.component_id)
        if c.component_type == "SPOKES":
            spokes = (c, i)
    since_utc, since = "", None
    out: dict = {"wheel_id": wheel.id, "component_id": None, "label": None, "specs": {}, "from_product": []}
    if spokes:
        c, inst = spokes
        prod = json.loads(c.product.specs_json or "{}") if c.product else {}
        own = json.loads(c.specs_json or "{}")
        keys = ("count", "model", "length_mm", "length_drive_mm", "length_non_drive_mm", "nipples")
        out.update({"component_id": c.id, "label": c.label,
                    "product": f"{c.product.maker or ''} {c.product.model}".strip() if c.product else None,
                    "specs": {k: own.get(k, prod.get(k)) for k in keys if own.get(k, prod.get(k)) not in (None, "")},
                    "from_product": [k for k in keys if k not in own and prod.get(k) not in (None, "")]})
        since_utc, since = inst.installed_utc, inst.installed_at[:10]
    relace = _last_event(session, wheel.id, ["WHEEL_RELACE"])
    if relace and relace.sort_utc > since_utc:
        since_utc, since = relace.sort_utc, relace.performed_on
    broken = list(session.scalars(select(MaintenanceEvent).where(
        MaintenanceEvent.component_id == wheel.id, MaintenanceEvent.action_code == "SPOKE_REPLACE",
        MaintenanceEvent.voided_at.is_(None), MaintenanceEvent.sort_utc > since_utc)))
    out.update({"broken": len(broken), "since": since,
                "relace_after": int(settings.get(session, "spoke_relace_after") or 3)})
    return out


def _spoke_items(session: Session, comp: Component) -> list[dict]:
    info = spoke_info(session, comp)
    n, limit = info["broken"], info["relace_after"]
    if n == 0:
        return []
    status = "ATTENTION" if n >= limit else "DUE_SOON" if n == limit - 1 else "OK"
    since = f"since it was laced ({info['since']})" if info["since"] else "since tracking started"
    advice = (f"time to re-lace it with new spokes (your setting: after {limit}, under Settings)" if n >= limit
              else f"re-lace with new spokes after {limit}")
    return [{"rule_code": "SPOKE_RELACE", "name": "Re-lace wheel with new spokes", "action_code": "WHEEL_RELACE",
             "component_id": comp.id, "component": comp.label, "component_type": comp.component_type,
             "status": status, "broken_spokes": n,
             "explanation": f"{n} broken spoke{'' if n == 1 else 's'} replaced on {comp.label} {since}: {advice}. "
                            "Logging a re-lace (or fitting a new spoke set) starts the count again."}]


def _event_based_items(session: Session, comp: Component) -> list[dict]:
    """Attention raised by something that happened elsewhere: a crash (hanger), a worn chain (cassette,
    chainrings), broken spokes (wheel). Each stays until the part's own check is logged after it."""
    out: list[dict] = []
    t = comp.component_type
    if t in ("FRONT_WHEEL", "REAR_WHEEL"):
        return _spoke_items(session, comp)
    if t not in ("DERAILLEUR_HANGER", "CASSETTE", "CHAINRING"):
        return out
    loc = location(session, comp)
    bike_id = loc.get("bike_id")
    inst = open_installation(session, comp.id)
    if bike_id is None or inst is None:
        return out
    check = {"DERAILLEUR_HANGER": "HANGER_ALIGN", "CASSETTE": "CASSETTE_INSPECT", "CHAINRING": "CHAINRING_INSPECT"}[t]
    last = _last_event(session, comp.id, [check])
    cutoff = max(inst.installed_utc, last.sort_utc if last else "")
    name = ACTIONS[check].name
    row = {"rule_code": f"ATTENTION_AFTER_{check}", "name": name, "action_code": check, "component_id": comp.id,
           "component": comp.label, "component_type": t, "status": "ATTENTION"}
    if t == "DERAILLEUR_HANGER":
        crash = _last_crash(session, bike_id, cutoff)
        if crash and (not last or last.performed_on < crash.entry_on):
            out.append({**row, "explanation": f"Crash on {crash.entry_on}: check the hanger alignment before the "
                                              f"next ride (a bent hanger shifts badly and can put the derailleur "
                                              f"into the spokes)."})
        return out
    worn = session.scalar(select(MaintenanceEvent).join(Component, Component.id == MaintenanceEvent.component_id).where(
        MaintenanceEvent.bike_id == bike_id, MaintenanceEvent.action_code == "CHAIN_MEASURE_WEAR",
        MaintenanceEvent.outcome == "AT_LIMIT", MaintenanceEvent.voided_at.is_(None),
        MaintenanceEvent.sort_utc > cutoff).order_by(MaintenanceEvent.sort_utc.desc()))
    replaced = session.scalar(select(Installation).join(Component, Component.id == Installation.component_id).where(
        Installation.bike_id == bike_id, Component.component_type == "CHAIN", Installation.voided_at.is_(None),
        Installation.removed_utc > cutoff, Installation.removal_outcome.in_(OUT_OF_USE))
        .order_by(Installation.removed_utc.desc()))
    what = t.lower().replace("_", " ")
    if replaced:
        old = session.get(Component, replaced.component_id)
        out.append({**row, "explanation": f"Worn chain {old.label} taken off on {replaced.removed_at[:10]}: check "
                                          f"the {what} for wear (a worn {what} skips with a new chain)."})
    elif worn:
        out.append({**row, "explanation": f"Chain measured at its wear limit on {worn.performed_on}: check the {what} "
                                          f"too when you replace the chain."})
    return out


def component_status(session: Session, comp: Component, today: date | None = None) -> list[dict]:
    rows = [rule_status(session, comp, r, today) for r in effective_rules(session, comp, include_disabled=True)]
    rows += attention_items(session, comp)
    rows += _event_based_items(session, comp)
    return sorted(rows, key=lambda r: SEVERITY[r["status"]])


def bike_attention_items(session: Session, bike: Bike) -> list[dict]:
    """Bike-level findings that need attention: a crash without a frame inspection since, or a bike
    check whose latest result says something is wrong (frame damage, Di2 error)."""
    out = []
    base = {"component_id": None, "component": None, "component_type": BIKE, "bike_id": bike.id, "bike": bike.name,
            "status": "ATTENTION"}
    sub = _Subject(session, bike=bike)
    for code, action in ACTIONS.items():
        if not action.attention_outcomes or BIKE not in action.targets:
            continue
        last = sub.last_event([code])
        if last and last.outcome in action.attention_outcomes:
            out.append({**base, "rule_code": f"ATTENTION_{code}", "name": action.name, "action_code": code,
                        "event_id": last.id,
                        "explanation": f"{action.name} on {last.performed_on}: {last.outcome.replace('_', ' ').lower()}"
                                       f"{' — ' + last.symptom if last.symptom else ''}. Stays until a newer "
                                       f"{action.name.lower()} records a different result."})
    crash = _last_crash(session, bike.id)
    if crash:
        insp = sub.last_event(["FRAME_INSPECT"])
        if not insp or insp.performed_on < crash.entry_on:
            out.append({**base, "rule_code": "ATTENTION_CRASH", "name": "Frame and fork inspection after a crash",
                        "action_code": "FRAME_INSPECT", "journal_id": crash.id,
                        "explanation": f"Crash on {crash.entry_on}: inspect frame and fork before riding hard "
                                       "(cracks, splinters, milky patches on carbon: do not ride). Check the bars, "
                                       "levers, hanger and wheels too. Stays until a frame and fork inspection "
                                       "is logged."})
    return out


def bike_status(session: Session, bike: Bike, today: date | None = None) -> list[dict]:
    rows = [bike_rule_status(session, bike, r, today) for r in effective_bike_rules(session, bike, include_disabled=True)]
    rows += bike_attention_items(session, bike)
    return sorted(rows, key=lambda r: SEVERITY[r["status"]])


def queue(session: Session, *, bike_id: int | None = None, include_ok: bool = False,
          today: date | None = None) -> list[dict]:
    """What needs attention next and why, for installed parts."""
    out = []
    hidden = ("DISABLED", "DONE_THIS_CYCLE", "NOT_APPLICABLE")
    for comp in session.scalars(select(Component).where(Component.status == "ACTIVE").order_by(Component.label)):
        loc = location(session, comp)
        if loc["state"] not in ("INSTALLED", "IN_USE") or (bike_id is not None and loc.get("bike_id") != bike_id):
            continue
        for row in component_status(session, comp, today):
            if row["status"] in hidden or (row["status"] == "OK" and not include_ok):
                continue
            out.append({**row, "bike_id": loc.get("bike_id"), "bike": loc.get("bike"), "slot": loc.get("slot")})
    bikes = select(Bike).where(Bike.status == "ACTIVE")
    if bike_id is not None:
        bikes = select(Bike).where(Bike.id == bike_id)
    for bike in session.scalars(bikes):
        for row in bike_status(session, bike, today):
            if row["status"] in hidden or (row["status"] == "OK" and not include_ok):
                continue
            out.append({**row, "slot": None})
    _add_chain_swaps(session, out)
    return sorted(out, key=lambda r: (SEVERITY[r["status"]], r.get("bike") or "", r["component"] or ""))


def _add_chain_swaps(session: Session, rows: list[dict]) -> None:
    """A hot-wax task on a chain in a rotation says what to do instead: swap to the next waxed chain, or wax
    the dirty ones (services/chains.py)."""
    from bikelog.services import chains
    rotations: dict[int, dict] = {}
    for r in rows:
        if r.get("action_code") != "WAX_HOT" or r["status"] not in chains.SOON or not r.get("bike_id"):
            continue
        rot = rotations.get(r["bike_id"]) or rotations.setdefault(r["bike_id"], chains.rotation(session, r["bike_id"]))
        p = rot["prompt"]
        if p and rot["on"] == r["component_id"] and len(rot["chains"]) > 1:
            r["rotation"] = p | {"bike_id": r["bike_id"]}
            r["explanation"] += f" Chain rotation: {p['text']}"


# ---------------------------------------------------------------- chains & brakes

def chain_overview(session: Session) -> list[dict]:
    return [chain_row(session, comp) for comp in session.scalars(
        select(Component).where(Component.component_type == "CHAIN").order_by(Component.label))]


def chain_row(session: Session, comp: Component) -> dict:
    """One chain's state for the chain list and the rotation (services/chains.py)."""
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
    waxes = session.scalar(select(func.count()).select_from(MaintenanceEvent).where(
        MaintenanceEvent.component_id == comp.id, MaintenanceEvent.action_code == "WAX_HOT",
        MaintenanceEvent.voided_at.is_(None)))
    return {"component_id": comp.id, "label": comp.label, "mark": comp.mark, "state": state, "text": text,
            "lifetime_km": lifetime, "km_since_hot_wax": since_hot,
            "last_hot_wax": hot.performed_on if hot else None, "wax_cycles": waxes,
            "rotation_bike_id": comp.rotation_bike_id,
            "last_wear": {"date": wear.performed_on, "value": wear.measurement_value,
                          "unit": wear.measurement_unit, "outcome": wear.outcome} if wear else None,
            "location": loc}


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
