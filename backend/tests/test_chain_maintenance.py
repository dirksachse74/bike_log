from datetime import date

import pytest

from bikelog.services import inventory as inv
from bikelog.services import maintenance as m

from helpers import bike, km, part, ride

TODAY = date(2026, 10, 24)


def status(session, comp, code):
    return next(r for r in m.component_status(session, comp, TODAY) if r["rule_code"] == code)


@pytest.fixture()
def chain_bike(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-01")
    return b, chain


def test_260km_ride_triggers_liquid_wax(session, chain_bike):
    """Acceptance 1."""
    b, chain = chain_bike
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "OK"
    ride(session, b, "2026-10-02", 260)
    s = status(session, chain, "CHAIN_LIQUID_WAX")
    assert s["status"] == "DUE"
    assert "260 km since hot wax on 2026-10-01" in s["explanation"] and "250–300 km" in s["explanation"]
    assert any(t["rule_code"] == "CHAIN_LIQUID_WAX" for t in m.queue(session, today=TODAY))


def test_liquid_wax_leaves_hot_wax_due_at_500km(session, chain_bike):
    """Acceptance 2."""
    b, chain = chain_bike
    ride(session, b, "2026-10-02", 270)
    m.log_event(session, action_code="WAX_LIQUID", component_id=chain.id, at="2026-10-03")
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "DONE_THIS_CYCLE"
    ride(session, b, "2026-10-04", 229)
    assert status(session, chain, "CHAIN_HOT_WAX")["status"] == "DUE_SOON"   # 499 km
    ride(session, b, "2026-10-05", 1)
    hot = status(session, chain, "CHAIN_HOT_WAX")
    assert hot["status"] == "DUE" and hot["used_km"] == 500
    assert "500 km since last hot wax on 2026-10-01" in hot["explanation"]
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "DONE_THIS_CYCLE"  # still one per cycle


def test_top_up_window_states(session, chain_bike):
    b, chain = chain_bike
    ride(session, b, "2026-10-02", 230)
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "DUE_SOON"
    ride(session, b, "2026-10-03", 80)
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "OVERDUE"


def test_hot_wax_starts_new_cycle_and_clears_obsolete_top_up(session, chain_bike):
    b, chain = chain_bike
    ride(session, b, "2026-10-02", 260)
    snooze = m.snooze(session, chain.id, "CHAIN_LIQUID_WAX", extra_km=100)
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "SNOOZED"
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-04")
    assert snooze.cleared_at is not None
    s = status(session, chain, "CHAIN_LIQUID_WAX")
    assert s["status"] == "OK" and s["used_km"] == 0 and s["cycle_started"] == "2026-10-04"
    assert status(session, chain, "CHAIN_HOT_WAX")["used_km"] == 0
    ride(session, b, "2026-10-05", 255)
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "DUE"


def test_wear_inspection_is_independent(session, chain_bike):
    b, chain = chain_bike
    ride(session, b, "2026-10-02", 950)
    assert status(session, chain, "CHAIN_WEAR_CHECK")["status"] == "DUE_SOON"
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-10-03")
    assert status(session, chain, "CHAIN_WEAR_CHECK")["used_km"] == 950        # waxing does not reset wear
    m.log_event(session, action_code="CHAIN_MEASURE_WEAR", component_id=chain.id, at="2026-10-03",
                measurement_value=0.3, measurement_unit="%", outcome="OK")
    assert status(session, chain, "CHAIN_WEAR_CHECK")["used_km"] == 0
    assert status(session, chain, "CHAIN_HOT_WAX")["used_km"] == 0              # measuring does not wax


def test_wear_at_limit_needs_attention(session, chain_bike):
    _, chain = chain_bike
    m.log_event(session, action_code="CHAIN_MEASURE_WEAR", component_id=chain.id, at="2026-10-03",
                measurement_value=0.5, measurement_unit="%", outcome="AT_LIMIT")
    att = [r for r in m.component_status(session, chain, TODAY) if r["status"] == "ATTENTION"]
    assert att and "at limit" in att[0]["explanation"]


def test_chain_swap_allocates_subsequent_mileage(session, chain_bike):
    """Acceptance 3."""
    b, chain_a = chain_bike
    chain_b = part(session, "CHAIN", "Chain B")
    ride(session, b, "2026-10-02", 120)
    inv.replace(session, chain_a.id, new_component_id=chain_b.id, at="2026-10-03T09:00")
    ride(session, b, "2026-10-03T10:00", 40)
    ride(session, b, "2026-10-04", 60)
    assert km(session, chain_a) == 120 and km(session, chain_b) == 100
    assert status(session, chain_a, "CHAIN_HOT_WAX")["used_km"] == 120   # stored chain stops accumulating
    ride(session, b, "2026-10-05", 10)
    assert km(session, chain_a) == 120


def test_spare_chain_readiness(session, chain_bike):
    b, chain_a = chain_bike
    b2 = part(session, "CHAIN", "Chain B")
    c3 = part(session, "CHAIN", "Chain C")
    inv.install(session, b2.id, bike_id=bike(session, "BMC").id, at="2026-08-01", until="2026-09-01")
    m.log_event(session, action_code="WAX_HOT", component_id=b2.id, at="2026-09-02")
    states = {c["label"]: c["state"] for c in m.chain_overview(session)}
    assert states == {"Chain A": "INSTALLED", "Chain B": "READY_TO_INSTALL", "Chain C": "NEW_UNWAXED"}
    inv.install(session, c3.id, bike_id=bike(session, "Cube").id, at="2026-10-01")
    ride(session, session.get(type(b), inv.location(session, c3)["bike_id"]), "2026-10-02", 30)
    inv.remove(session, c3.id, at="2026-10-03")
    m.log_event(session, action_code="WAX_HOT", component_id=c3.id, at="2026-09-01")   # older than the ride
    assert {c["label"]: c["state"] for c in m.chain_overview(session)}["Chain C"] == "NEEDS_HOT_WAX"


def test_intervals_are_configurable(session, chain_bike):
    b, chain = chain_bike
    hot = next(r for r in m.effective_rules(session, chain) if r.rule_code == "CHAIN_HOT_WAX")
    liquid = next(r for r in m.effective_rules(session, chain) if r.rule_code == "CHAIN_LIQUID_WAX")
    m.update_rule(session, hot.id, interval_km=400)
    m.update_rule(session, liquid.id, window_min_km=200, window_max_km=220)
    ride(session, b, "2026-10-02", 210)
    assert status(session, chain, "CHAIN_LIQUID_WAX")["status"] == "DUE"
    ride(session, b, "2026-10-03", 190)
    assert status(session, chain, "CHAIN_HOT_WAX")["status"] == "DUE"
    from bikelog.services.errors import DomainError
    with pytest.raises(DomainError):
        m.update_rule(session, liquid.id, window_min_km=300, window_max_km=250)


def test_no_hot_wax_recorded_is_insufficient_information(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Used chain", prior_usage="UNKNOWN")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    s = status(session, chain, "CHAIN_HOT_WAX")
    assert s["status"] == "INSUFFICIENT_INFO" and "Insufficient information" in s["explanation"]
