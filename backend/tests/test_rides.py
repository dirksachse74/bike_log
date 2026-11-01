import pytest

from bikelog.services import inventory as inv
from bikelog.services import rides
from bikelog.services.errors import DomainError
from bikelog.services.operations import run_once, with_change
from bikelog.services.usage import bike_usage, component_ledger, component_usage

from helpers import bike, km, part, ride


@pytest.fixture()
def setup(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    return b, chain


def test_edit_remove_restore_change_totals_exactly_once(session, setup):
    """Acceptance 4: editing, removing and restoring a ride changes totals exactly once."""
    b, chain = setup
    r = ride(session, b, "2026-10-05", 80)
    assert km(session, chain) == 80
    rides.edit_ride(session, r.id, {"distance_km": 65})
    rides.edit_ride(session, r.id, {"distance_km": 65})        # repeat: no further change
    assert km(session, chain) == 65
    rides.exclude_ride(session, r.id, "duplicate of Strava ride")
    rides.exclude_ride(session, r.id)
    assert km(session, chain) == 0
    rides.restore_ride(session, r.id)
    rides.restore_ride(session, r.id)
    assert km(session, chain) == 65
    assert bike_usage(session, b)["total_km"] == 65


def test_change_preview_and_notice(session, setup):
    b, chain = setup
    r = ride(session, b, "2026-10-05", 80)
    _, change = with_change(session, lambda: rides.edit_ride(session, r.id, {"distance_km": 65}), dry_run=True)
    assert change["preview"] and change["deltas"][0]["delta_km"] == -15
    assert change["notice"].startswith("Preview: Chain A −15.0 km")
    assert km(session, chain) == 80                              # nothing saved
    _, change = with_change(session, lambda: rides.edit_ride(session, r.id, {"distance_km": 65}))
    assert km(session, chain) == 65 and change["deltas"][0]["after_km"] == 65


def test_client_op_id_makes_repeated_submission_a_noop(session, setup):
    b, chain = setup
    calls = []

    def add():
        r = ride(session, b, "2026-10-06", 30)
        calls.append(r.id)
        return {"ride_id": r.id}
    first = run_once(session, "op-123", "ride.add", add)
    second = run_once(session, "op-123", "ride.add", add)
    assert first["ride_id"] == second["ride_id"] and second["repeated"] and len(calls) == 1
    assert km(session, chain) == 30


def test_assign_bike_and_equipment(session, setup):
    b, chain_a = setup
    chain_b = part(session, "CHAIN", "Chain B")
    r = ride(session, b, "2026-10-07", 50, equipment={"CHAIN": chain_b.id})   # explicit beats history
    assert km(session, chain_a) == 0 and km(session, chain_b) == 50
    rides.clear_equipment(session, r.id, "CHAIN")
    assert km(session, chain_a) == 50 and km(session, chain_b) == 0
    other = bike(session, "BMC")
    rides.edit_ride(session, r.id, {"bike_id": other.id})
    assert km(session, chain_a) == 0


def test_starting_mileage_with_effective_date_and_estimate(session):
    b = bike(session, starting_km=17000, starting_date="2026-09-01", starting_is_estimate=True)
    chain = part(session, "CHAIN", "Chain A", prior_usage="UNKNOWN")
    inv.install(session, chain.id, bike_id=b.id, at="2026-08-01")
    ride(session, b, "2026-08-20", 100)                           # before the starting date
    inv.set_starting_usage(session, component_id=chain.id, km=1000, effective="2026-09-01", is_estimate=True)
    ride(session, b, "2026-09-10", 78.4)
    u = component_usage(session, chain)
    assert u["total_km"] == 1078.4 and u["certainty"] == "ESTIMATED" and u["starting_is_estimate"]
    ledger = component_ledger(session, chain)
    assert [e["kind"] for e in ledger] == ["RIDE", "STARTING", "RIDE"]
    assert ledger[0]["counted"] is False and ledger[0]["state"] == "IN_BASELINE"
    assert ledger[-1]["running_km"] == 1078.4
    bu = bike_usage(session, b)
    assert bu["total_km"] == 17078.4 and bu["certainty"] == "ESTIMATED"


def test_unknown_prior_usage_is_shown_as_minimum(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Old chain", prior_usage="UNKNOWN")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    ride(session, b, "2026-10-02", 20)
    u = component_usage(session, chain)
    assert u["is_minimum"] and u["certainty"] == "INCOMPLETE" and "unknown" in u["summary"]


def test_uncertain_assignment_is_flagged_and_marked(session, setup):
    b, chain = setup
    r = ride(session, b, "2026-10-08", 40, assignment_uncertain=True, uncertainty_note="BMC or TIME?")
    row = rides.ride_row(session, r)
    assert any(f["code"] == "UNCERTAIN_ASSIGNMENT" for f in row["flags"])
    assert component_usage(session, chain)["uncertain_km"] == 40


def test_date_only_change_on_ride_day_is_flagged(session, setup):
    b, chain_a = setup
    chain_b = part(session, "CHAIN", "Chain B")
    inv.remove(session, chain_a.id, at="2026-10-10")
    inv.install(session, chain_b.id, bike_id=b.id, at="2026-10-10")
    r = ride(session, b, "2026-10-10T17:30", 30)
    row = rides.ride_detail(session, r)
    assert any(f["code"] == "AMBIGUOUS_CHANGE_DATE" and f["slot"] == "CHAIN" for f in row["flags"])
    assert km(session, chain_b) == 30 and component_usage(session, chain_b)["uncertain_km"] == 30
    rides.set_equipment(session, r.id, "CHAIN", chain_a.id, note="swapped after the ride")
    row = rides.ride_detail(session, r)
    assert not any(f["code"] == "AMBIGUOUS_CHANGE_DATE" for f in row["flags"])
    assert km(session, chain_a) == 30 and km(session, chain_b) == 0


def test_trainer_configuration_excludes_removed_equipment(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    wheel = part(session, "REAR_WHEEL", "Rear wheel")
    tire = part(session, "TIRE", "Rear tire")
    pads = part(session, "BRAKE_PADS", "Rear pads")
    for c, kw in ((chain, {"bike_id": b.id}), (wheel, {"bike_id": b.id}), (tire, {"parent_component_id": wheel.id}),
                  (pads, {"bike_id": b.id, "slot": "REAR_PADS"})):
        inv.install(session, c.id, at="2026-10-01", **kw)
    ride(session, b, "2026-10-02", 30, sport_type="VirtualRide")             # default trainer profile
    ride(session, b, "2026-10-03", 20, usage_profile_code="DIRECT_DRIVE_TRAINER")
    ride(session, b, "2026-10-04", 50)
    assert km(session, chain) == 100
    assert km(session, wheel) == 50 and km(session, tire) == 50 and km(session, pads) == 50


def test_missing_distance_is_not_zero(session, setup):
    b, chain = setup
    r = rides.add_manual_ride(session, bike_id=b.id, when="2026-10-09", distance=None, duration_s=3600)
    assert r.distance_km is None
    row = rides.ride_row(session, r)
    assert any(f["code"] == "MISSING_DISTANCE" for f in row["flags"])
    u = component_usage(session, chain)
    assert u["missing_distance_rides"] == 1 and u["hours"] == 1


def test_miles_are_converted_at_full_precision(session, setup):
    b, chain = setup
    rides.add_manual_ride(session, bike_id=b.id, when="2026-10-09", distance=10, unit="mi")
    assert km(session, chain) == pytest.approx(16.09344)


def test_ride_needs_bike_unless_uncertain(session):
    with pytest.raises(DomainError):
        rides.add_manual_ride(session, bike_id=None, when="2026-10-09", distance=10)
    r = rides.add_manual_ride(session, bike_id=None, when="2026-10-09", distance=10, assignment_uncertain=True)
    assert any(f["code"] == "NO_BIKE" for f in rides.ride_row(session, r)["flags"])


def test_possible_duplicate_is_flagged_not_merged(session, setup):
    b, chain = setup
    ride(session, b, "2026-10-11", 50)
    r2 = ride(session, b, "2026-10-11", 50.8)
    assert any(f["code"] == "POSSIBLE_DUPLICATE" for f in rides.ride_row(session, r2)["flags"])
    assert km(session, chain) == pytest.approx(100.8)


def test_rebuild_is_deterministic(session, setup):
    from bikelog.services.allocation import rebuild_all
    from bikelog.services.usage import component_totals
    b, chain = setup
    for d, k in (("2026-10-02", 10), ("2026-10-03", 20)):
        ride(session, b, d, k)
    before = component_totals(session)
    rebuild_all(session, "Europe/Berlin")
    rebuild_all(session, "Europe/Berlin")
    assert component_totals(session) == before


def test_road_ride_on_bike_without_wheels_is_flagged(session, setup):
    """UAT B1: the km would silently miss the wheels and tires."""
    b, chain = setup
    codes = lambda r: {f["code"] for f in rides.ride_row(session, r)["flags"]}
    road = ride(session, b, "2026-10-05", 80)
    zwift = ride(session, b, "2026-10-06", 30, sport_type="VirtualRide")
    assert "NO_WHEELS" in codes(road) and "NO_WHEELS" not in codes(zwift)
    wheel = part(session, "REAR_WHEEL", "Rear wheel")
    inv.install(session, wheel.id, bike_id=b.id, at="2026-10-04")
    session.refresh(road)
    assert "NO_WHEELS" not in codes(road)


def test_rides_before_tracking_or_purchase_are_explained(session):
    """UAT B3: a reason on the ride, a flag before the purchase date, ride count agrees with km."""
    b = bike(session, starting_km=850, starting_date="2026-09-01", starting_is_estimate=True)
    early = ride(session, b, "2025-12-31", 40)
    before = ride(session, b, "2026-08-20", 30)
    ride(session, b, "2026-09-10", 50)
    inv.update_bike(session, b.id, purchase_date="2026-03-01")     # set later: the early ride is flagged now
    usage = bike_usage(session, b)
    assert usage["ride_count"] == 1 and usage["rides_before_start"] == 2 and usage["total_km"] == 900
    detail = rides.ride_detail(session, before)
    assert detail["counting_note"].startswith("Before tracking started")
    assert "BEFORE_PURCHASE" in {f["code"] for f in rides.ride_row(session, early)["flags"]}
    assert "BEFORE_PURCHASE" not in {f["code"] for f in rides.ride_row(session, before)["flags"]}


def test_change_notice_is_short_for_many_parts():
    from bikelog.services.operations import notice
    deltas = [{"label": f"Part {i}", "delta_km": 80.0} for i in range(20)]
    assert notice(deltas, False) == "+80.0 km on 20 parts."
    assert notice(deltas, True).startswith("Preview: Part 0 +80.0 km; Part 1")
    mixed = deltas[:5] + [{"label": "Rear tire", "delta_km": -10.0}]
    assert notice(mixed, False) == "6 parts changed: Part 0 +80.0 km; Part 1 +80.0 km; Part 2 +80.0 km; and 3 more."


def test_ride_summary_with_bike_totals_this_year_and_month(session):
    from datetime import date

    from bikelog.services.rides import ride_detail, ride_summary
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2025-12-01", bike_id=b.id)
    ride(session, b, "2025-12-20", 30, duration_s=3600)
    ride(session, b, "2026-09-05", 50, duration_s=2 * 3600)
    r = ride(session, b, "2026-10-12", 40, duration_s=5400)
    s = ride_summary(session, r, today=date(2026, 10, 26))
    assert s["km"] == 40 and s["hours"] == 1.5
    assert s["bike"]["total_km"] == 120 and s["bike"]["total_hours"] == 4.5
    assert s["bike"]["year"] == {"label": "2026", "km": 90, "hours": 3.5, "rides": 2}
    assert s["bike"]["month"] == {"label": "October 2026", "km": 40, "hours": 1.5, "rides": 1}
    eq = ride_detail(session, r)["equipment"]
    assert eq[0]["label"] == "Chain A" and eq[0]["hours"] == 1.5
