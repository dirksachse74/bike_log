"""Copy default service rules and usage profiles into the database (idempotent, never overwrites edits)."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from bikelog.catalog import DEFAULT_PROFILES, DEFAULT_RULES
from bikelog.models import ServiceRule, UsageProfile


def ensure_reference_data(session: Session) -> None:
    have_rules = {(r.component_type, r.rule_code) for r in session.scalars(
        select(ServiceRule).where(ServiceRule.component_type.is_not(None)))}
    for d in DEFAULT_RULES:
        if (d.component_type, d.rule_code) in have_rules:
            continue
        session.add(ServiceRule(
            rule_code=d.rule_code, name=d.name, component_type=d.component_type, action_code=d.action_code,
            trigger=d.trigger, interval_km=d.interval_km, interval_months=d.interval_months,
            window_min_km=d.window_min_km, window_max_km=d.window_max_km, cycle_action_code=d.cycle_action_code,
            reset_actions_json=json.dumps(list(d.reset_actions or (d.action_code,))),
            warn_km=d.warn_km, warn_days=d.warn_days, origin=d.origin, active=True,
        ))
    have_profiles = set(session.scalars(select(UsageProfile.code)))
    for p in DEFAULT_PROFILES:
        if p.code in have_profiles:
            continue
        session.add(UsageProfile(code=p.code, name=p.name, kind=p.kind,
                                 excluded_slots_json=json.dumps(list(p.excluded_slots)),
                                 excluded_types_json=json.dumps(list(p.excluded_types)), notes=p.notes))
    session.flush()
