from datetime import date

import pytest

from bikelog.models import MaintenanceEvent
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services.errors import DomainError

from helpers import bike, part, ride

TODAY = date(2026, 10, 24)


def status(session, comp, code, today=TODAY):
    return next(r for r in m.component_status(session, comp, today) if r["rule_code"] == code)


@pytest.fixture()
def brakes(session):
    b = bike(session)
    front = part(session, "BRAKE_CIRCUIT", "Front brake")
    rear = part(session, "BRAKE_CIRCUIT", "Rear brake")
    inv.install(session, front.id, bike_id=b.id, slot="FRONT_BRAKE", at="2025-01-01")
    inv.install(session, rear.id, bike_id=b.id, slot="REAR_BRAKE", at="2025-01-01")
    return b, front, rear


def test_front_and_rear_circuits_are_independent(session, brakes):
    _, front, rear = brakes
    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=rear.id, at="2026-03-01")
    assert status(session, rear, "BRAKE_FLUID")["due_date"] == "2028-03-01"
    assert status(session, front, "BRAKE_FLUID")["due_date"] == "2027-01-01"   # new part, since install
    over = {b["position"]: b for b in m.brake_overview(session)}
    assert set(over) == {"Front", "Rear"}


def test_full_fluid_replacement_resets_two_year_interval(session, brakes):
    _, front, _ = brakes
    s = status(session, front, "BRAKE_FLUID", today=date(2027, 2, 1))
    assert s["status"] == "OVERDUE"
    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=front.id, at="2027-02-01")
    s = status(session, front, "BRAKE_FLUID", today=date(2027, 2, 1))
    assert s["status"] == "OK" and s["due_date"] == "2029-02-01"
    assert "interval 24 months" in s["explanation"]


def test_bleed_records_details_and_does_not_reset_fluid_deadline(session, brakes):
    """Acceptance 6."""
    _, _, rear = brakes
    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=rear.id, at="2026-03-01")
    before = status(session, rear, "BRAKE_FLUID")["due_date"]
    ev = m.log_event(session, action_code="BRAKE_BLEED", component_id=rear.id, at="2026-10-12",
                     symptom="spongy lever", work_done="lever bleed, 5 ml mineral oil", outcome="IMPROVED")
    after = status(session, rear, "BRAKE_FLUID")
    assert after["due_date"] == before == "2028-03-01"
    assert "bleed on 2026-10-12 does not reset" in after["explanation"]
    stored = session.get(MaintenanceEvent, ev.id)
    assert (stored.symptom, stored.work_done, stored.outcome) == ("spongy lever", "lever bleed, 5 ml mineral oil",
                                                                 "IMPROVED")
    bleed = next(b for b in m.brake_overview(session) if b["component_id"] == rear.id)["last_bleed"]
    assert bleed["outcome"] == "IMPROVED"


def test_unknown_fluid_history_is_insufficient_information(session):
    b = bike(session)
    front = part(session, "BRAKE_CIRCUIT", "Front brake", prior_usage="UNKNOWN")
    inv.install(session, front.id, bike_id=b.id, slot="FRONT_BRAKE", at="2025-01-01")
    assert status(session, front, "BRAKE_FLUID")["status"] == "INSUFFICIENT_INFO"


def test_wheel_inspection_bearing_and_freehub_are_separate(session):
    b = bike(session)
    rear = part(session, "REAR_WHEEL", "Rear wheel")
    front = part(session, "FRONT_WHEEL", "Front wheel")
    inv.install(session, rear.id, bike_id=b.id, at="2026-01-01")
    inv.install(session, front.id, bike_id=b.id, at="2026-01-01")
    ride(session, b, "2026-02-01", 5200)
    codes = {r["rule_code"]: r for r in m.component_status(session, rear, TODAY)}
    assert {"REAR_WHEEL_INSPECTION", "REAR_HUB_BEARINGS", "FREEHUB"} <= set(codes)
    assert "FREEHUB" not in {r["rule_code"] for r in m.component_status(session, front, TODAY)}
    m.log_event(session, action_code="FREEHUB_SERVICE", component_id=rear.id, at="2026-03-01")
    assert status(session, rear, "FREEHUB")["used_km"] == 0
    assert status(session, rear, "REAR_HUB_BEARINGS")["used_km"] == 5200
    assert status(session, rear, "REAR_WHEEL_INSPECTION")["used_km"] == 5200
    with pytest.raises(DomainError):
        m.log_event(session, action_code="FREEHUB_SERVICE", component_id=front.id, at="2026-03-01")


def test_component_specific_rules_by_distance_or_time(session):
    b = bike(session)
    saddle = part(session, "SADDLE", "Saddle")
    inv.install(session, saddle.id, bike_id=b.id, at="2026-01-01")
    by_km = m.set_component_rule(session, saddle.id, action_code="INSPECT", name="Check rails", interval_km=2000)
    by_time = m.set_component_rule(session, saddle.id, action_code="CLEAN", name="Clean", interval_months=3)
    ride(session, b, "2026-02-01", 1950)
    st = {r["rule_code"]: r for r in m.component_status(session, saddle, TODAY)}
    assert st[by_km.rule_code]["status"] == "DUE_SOON"
    assert st[by_time.rule_code]["status"] == "OVERDUE" and st[by_time.rule_code]["due_date"] == "2026-04-01"


def test_component_override_replaces_type_default(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-01")
    m.set_component_rule(session, chain.id, rule_code="CHAIN_HOT_WAX", interval_km=300, origin="MANUFACTURER")
    ride(session, b, "2026-10-02", 300)
    s = status(session, chain, "CHAIN_HOT_WAX")
    assert s["status"] == "DUE" and s["origin"] == "MANUFACTURER"
    m.set_component_rule(session, chain.id, rule_code="CHAIN_WEAR_CHECK", active=False)
    assert status(session, chain, "CHAIN_WEAR_CHECK")["status"] == "DISABLED"


def test_snooze_records_no_maintenance(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-01")
    ride(session, b, "2026-10-02", 510)
    n_events = session.query(MaintenanceEvent).count()
    m.snooze(session, chain.id, "CHAIN_HOT_WAX", until_date="2026-10-30")
    s = status(session, chain, "CHAIN_HOT_WAX")
    assert s["status"] == "SNOOZED" and s["underlying_status"] == "DUE" and "no maintenance recorded" in s["explanation"]
    assert session.query(MaintenanceEvent).count() == n_events
    assert status(session, chain, "CHAIN_HOT_WAX", today=date(2026, 10, 30))["status"] == "DUE"   # snooze ended


def test_every_due_task_explains_itself(session, brakes):
    b, front, rear = brakes
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-01")
    ride(session, b, "2026-10-02", 520)
    q = m.queue(session, today=date(2027, 6, 1))
    assert q and all(t["explanation"] and t["status"] != "OK" for t in q)
    assert any("since last hot wax" in t["explanation"] for t in q)


def test_batch_logging_and_void(session):
    b1, b2 = bike(session), bike(session, "BMC")
    a, c = part(session, "CHAIN", "Chain A"), part(session, "CHAIN", "Chain B")
    inv.install(session, a.id, bike_id=b1.id, at="2026-10-01")
    inv.install(session, c.id, bike_id=b2.id, at="2026-10-01")
    evs = m.log_batch(session, action_code="LUBE", at="2026-10-05", component_ids=[a.id, c.id])
    assert len({e.batch_ref for e in evs}) == 1 and evs[0].bike_id == b1.id
    m.void_event(session, evs[0].id, "logged on the wrong chain")
    assert m.events_for(session, component_id=a.id)[0]["voided"]


def test_consumables_purchase_use_separate(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    wax = m.add_consumable(session, kind="WAX", name="Silca Hot Melt", unit="g", track_stock=True)
    m.consumable_txn(session, wax.id, kind="PURCHASE", qty=500, on="2026-09-01", cost_cents=3999)
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-01", consumable_id=wax.id,
                consumable_qty=20)
    stock = next(s for s in m.consumable_stock(session) if s["id"] == wax.id)
    assert stock["stock"] == {"qty": 480, "known": True} and stock["purchases"] == 1 and stock["uses"] == 1
