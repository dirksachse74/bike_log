"""Maintenance coverage: bike-level reminders (torque, frame after a crash, Di2), measurement limits,
bed-in after fitting, wet rides, worn chain → cassette check, shoes and cleats, setup-dependent rules."""
from datetime import date

import pytest

from bikelog.catalog import ACTIONS, outcome_from_measurement
from bikelog.models import Product
from bikelog.services import inventory as inv
from bikelog.services import journal
from bikelog.services import maintenance as m
from bikelog.services import rides as rides_svc
from bikelog.services import settings
from bikelog.services.errors import DomainError

from helpers import bike, km, part, ride


def status(session, comp, code, today=None):
    return next(r for r in m.component_status(session, comp, today) if r["rule_code"] == code)


def bike_row(session, b, code, today=None):
    return next(r for r in m.bike_status(session, b, today) if r["rule_code"] == code)


def test_measurements_set_the_outcome_from_the_limits(session):
    assert outcome_from_measurement(ACTIONS["PAD_MEASURE"], 2.0, "mm") == "OK"
    assert outcome_from_measurement(ACTIONS["PAD_MEASURE"], 0.8, "mm") == "LOW"
    assert outcome_from_measurement(ACTIONS["PAD_MEASURE"], 0.5, None) == "AT_LIMIT"
    assert outcome_from_measurement(ACTIONS["ROTOR_MEASURE"], 1.55, "mm") == "LOW"
    assert outcome_from_measurement(ACTIONS["CHAIN_MEASURE_WEAR"], 0.5, "%") == "AT_LIMIT"
    assert outcome_from_measurement(ACTIONS["CHAIN_MEASURE_WEAR"], 0.2, "%") == "OK"
    assert outcome_from_measurement(ACTIONS["CHAIN_MEASURE_WEAR"], 0.5, "mm") is None   # other unit: no guess
    b = bike(session)
    pads = part(session, "BRAKE_PADS", "L05A front")
    inv.install(session, pads.id, at="2026-09-01", bike_id=b.id, slot="FRONT_PADS")
    ev = m.log_event(session, action_code="PAD_MEASURE", at="2026-10-01", component_id=pads.id, measurement_value=0.8)
    assert ev.outcome == "LOW" and ev.measurement_unit == "mm"
    assert any(r["rule_code"] == "ATTENTION_PAD_MEASURE" for r in m.component_status(session, pads))
    # a typed outcome is kept as entered
    ev = m.log_event(session, action_code="PAD_MEASURE", at="2026-10-02", component_id=pads.id,
                     measurement_value=0.8, outcome="OK")
    assert ev.outcome == "OK"


def test_bike_torque_check_and_recheck_after_new_parts(session):
    b = bike(session)
    row = bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 1))
    assert row["status"] == "INSUFFICIENT_INFO" and row["component_id"] is None and row["bike"] == "TIME NXR"
    with pytest.raises(DomainError, match="pick the part"):
        m.log_event(session, action_code="PAD_MEASURE", at="2026-09-01", bike_id=b.id)
    m.log_event(session, action_code="TORQUE_CHECK", at="2026-09-01", bike_id=b.id)
    row = bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 10))
    assert row["status"] == "OK" and row["due_date"] == "2026-12-01"
    prod = Product(component_type="STEM", maker="Deda", model="Superzero", specs_json='{"torque_nm": "5"}')
    session.add(prod)
    session.flush()
    stem = part(session, "STEM", "Deda Superzero", product_id=prod.id)
    inv.install(session, stem.id, at="2026-09-05", bike_id=b.id)
    row = bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 10))
    assert row["status"] == "OK" and "Deda Superzero 5 Nm" in row["explanation"]      # not ridden yet
    ride(session, b, "2026-09-06", 40)
    row = bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 10))
    assert row["status"] == "DUE" and row["recheck"] == ["Deda Superzero"]
    assert any(t["rule_code"] == "BIKE_TORQUE_CHECK" and t["component_id"] is None
               for t in m.queue(session, bike_id=b.id, today=date(2026, 9, 10)))
    m.snooze(session, None, "BIKE_TORQUE_CHECK", bike_id=b.id, until_date="2026-09-20")
    assert bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 10))["status"] == "SNOOZED"
    m.log_event(session, action_code="TORQUE_CHECK", at="2026-09-11", bike_id=b.id)
    row = bike_row(session, b, "BIKE_TORQUE_CHECK", date(2026, 9, 12))
    assert row["status"] == "OK" and not row.get("recheck")
    # per bike: switch it off for this bike only
    m.set_bike_rule(session, b.id, "BIKE_TORQUE_CHECK", active=False)
    assert bike_row(session, b, "BIKE_TORQUE_CHECK")["status"] == "DISABLED"
    assert bike_row(session, bike(session, "BMC Roadmachine"), "BIKE_TORQUE_CHECK")["status"] == "INSUFFICIENT_INFO"


def test_crash_needs_frame_inspection_and_hanger_check(session):
    b = bike(session)
    hanger = part(session, "DERAILLEUR_HANGER", "NXR hanger")
    inv.install(session, hanger.id, at="2026-09-01", bike_id=b.id)
    r = ride(session, b, "2026-10-05", 60)
    journal.add(session, text="Slipped on wet leaves", ride_id=r.id, incident_type="CRASH")
    crash = bike_row(session, b, "ATTENTION_CRASH")
    assert crash["status"] == "ATTENTION" and "2026-10-05" in crash["explanation"]
    assert status(session, hanger, "ATTENTION_AFTER_HANGER_ALIGN")["status"] == "ATTENTION"
    m.log_event(session, action_code="FRAME_INSPECT", at="2026-10-05", bike_id=b.id, outcome="OK")
    m.log_event(session, action_code="HANGER_ALIGN", at="2026-10-06", component_id=hanger.id, outcome="STRAIGHTENED")
    assert not any(x["rule_code"] == "ATTENTION_CRASH" for x in m.bike_status(session, b))
    assert not any(x["rule_code"] == "ATTENTION_AFTER_HANGER_ALIGN" for x in m.component_status(session, hanger))
    m.log_event(session, action_code="FRAME_INSPECT", at="2026-10-07", bike_id=b.id, outcome="DAMAGE",
                symptom="crack at the dropout")
    assert bike_row(session, b, "ATTENTION_FRAME_INSPECT")["status"] == "ATTENTION"


def test_bed_in_once_after_fitting(session):
    b = bike(session)
    pads = part(session, "BRAKE_PADS", "New pads")
    inv.install(session, pads.id, at="2026-10-01", bike_id=b.id, slot="REAR_PADS")
    assert status(session, pads, "PAD_BED_IN")["status"] == "DUE"
    m.log_event(session, action_code="BED_IN", at="2026-10-01", component_id=pads.id)
    assert status(session, pads, "PAD_BED_IN")["status"] == "DONE_THIS_CYCLE"
    old = part(session, "BRAKE_PADS", "Old pads")
    inv.install(session, old.id, at="2026-09-01", bike_id=b.id, slot="FRONT_PADS")
    ride(session, b, "2026-09-02", 150)
    st = status(session, old, "PAD_BED_IN")
    assert st["status"] == "DONE_THIS_CYCLE" and "taken as done" in st["explanation"]


def test_wet_ride_makes_waxing_due(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2026-09-01", bike_id=b.id)
    m.log_event(session, action_code="WAX_HOT", at="2026-09-01", component_id=chain.id)
    r = ride(session, b, "2026-09-03", 50)
    assert status(session, chain, "CHAIN_HOT_WAX")["status"] == "OK"
    rides_svc.edit_ride(session, r.id, {"conditions": "WET"})
    st = status(session, chain, "CHAIN_HOT_WAX")
    assert st["status"] == "DUE" and "1 wet ride" in st["explanation"]
    m.log_event(session, action_code="WAX_HOT", at="2026-09-04", component_id=chain.id)
    assert status(session, chain, "CHAIN_HOT_WAX")["status"] == "OK"


def test_worn_chain_asks_for_a_cassette_check(session):
    b = bike(session)
    wheel = part(session, "REAR_WHEEL", "Rear wheel")
    cassette = part(session, "CASSETTE", "CS-R8100")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, wheel.id, at="2026-01-01", bike_id=b.id)
    inv.install(session, cassette.id, at="2026-01-01", parent_component_id=wheel.id)
    inv.install(session, chain.id, at="2026-01-01", bike_id=b.id)
    m.log_event(session, action_code="CHAIN_MEASURE_WEAR", at="2026-09-01", component_id=chain.id,
                measurement_value=0.5)
    assert "wear limit on 2026-09-01" in status(session, cassette, "ATTENTION_AFTER_CASSETTE_INSPECT")["explanation"]
    inv.replace(session, chain.id, at="2026-09-02", new={"label": "Chain B"}, old_outcome="DISCARDED")
    assert "Worn chain Chain A" in status(session, cassette, "ATTENTION_AFTER_CASSETTE_INSPECT")["explanation"]
    m.log_event(session, action_code="CASSETTE_INSPECT", at="2026-09-03", component_id=cassette.id, outcome="OK")
    assert not any(r["rule_code"].startswith("ATTENTION_AFTER") for r in m.component_status(session, cassette))


def test_shoes_and_cleats_count_rides_on_every_bike_while_in_use(session):
    b1, b2 = bike(session), bike(session, "BMC Roadmachine")
    shoes = part(session, "SHOES", "S-Phyre RC903")
    cleats = part(session, "CLEATS", "SM-SH11 yellow")
    inv.install(session, cleats.id, at="2026-09-01", parent_component_id=shoes.id)
    with pytest.raises(DomainError, match="rider gear"):
        inv.set_disposition(session, part(session, "CHAIN", "Chain X").id, "IN_USE", on="2026-09-01")
    ride(session, b1, "2026-08-30", 10)                       # before the shoes were in use
    inv.set_disposition(session, shoes.id, "IN_USE", on="2026-09-01")
    assert inv.location(session, shoes)["state"] == "IN_USE"
    assert inv.location(session, cleats)["text"].startswith("worn → S-Phyre RC903")
    ride(session, b1, "2026-09-02", 50)
    ride(session, b2, "2026-09-03", 70)
    assert km(session, shoes) == 120 and km(session, cleats) == 120
    st = status(session, cleats, "CLEAT_CHECK")
    assert st["status"] == "OK" and st["used_km"] == 120
    assert any(t["component_id"] == cleats.id for t in m.queue(session, include_ok=True))
    inv.set_disposition(session, shoes.id, "STORED", on="2026-09-04")
    ride(session, b1, "2026-09-05", 30)
    assert km(session, shoes) == 120 and km(session, cleats) == 120


def test_setup_dependent_rules_follow_shifting_and_default_tire_setup(session):
    b = bike(session)
    assert bike_row(session, b, "BIKE_DI2_CHECK")["status"] == "NOT_APPLICABLE"
    batt = part(session, "BATTERY", "BT-DN300")
    inv.install(session, batt.id, at="2026-09-01", bike_id=b.id)
    assert inv.shifting_of(session, b) == "ELECTRONIC"
    assert bike_row(session, b, "BIKE_DI2_CHECK")["status"] == "INSUFFICIENT_INFO"
    cable = part(session, "SHIFT_CABLE", "Rear cable")
    inv.install(session, cable.id, at="2026-09-01", bike_id=b.id, slot="SHIFT_CABLE_REAR")
    assert "set to electronic" in status(session, cable, "SHIFT_CABLE_CHECK")["explanation"]
    inv.update_bike(session, b.id, shifting="MECHANICAL")
    assert status(session, cable, "SHIFT_CABLE_CHECK")["status"] == "OK"
    assert bike_row(session, b, "BIKE_DI2_CHECK")["status"] == "NOT_APPLICABLE"
    with pytest.raises(DomainError):
        inv.update_bike(session, b.id, shifting="HYDRAULIC")
    # wheels without their own tube/tubeless setting use the default (inner tube)
    wheel = part(session, "FRONT_WHEEL", "Front wheel")
    tire = part(session, "TIRE", "GP5000")
    inv.install(session, wheel.id, at="2026-09-01", bike_id=b.id)
    inv.install(session, tire.id, at="2026-09-01", parent_component_id=wheel.id)
    assert status(session, tire, "TIRE_SEALANT_RENEW")["status"] == "NOT_APPLICABLE"
    settings.set_value(session, "default_tire_setup", "TUBELESS")
    assert status(session, tire, "TIRE_SEALANT_RENEW")["status"] == "OK"
    with pytest.raises(DomainError):
        settings.set_value(session, "default_tire_setup", "SLIME")


def test_service_before_km_from_before_date_reads_as_at_least(session):
    """UAT B2: km between the service and the starting-value date are inside the estimate."""
    b = bike(session)
    wheel = part(session, "REAR_WHEEL", "Used rear", prior_usage="UNKNOWN")
    inv.install(session, wheel.id, bike_id=b.id, at="2026-09-01")
    inv.set_starting_usage(session, component_id=wheel.id, km=1200, effective="2026-09-01", is_estimate=True)
    no_log = status(session, wheel, "FREEHUB", date(2026, 10, 20))
    assert no_log["status"] == "INSUFFICIENT_INFO" and "≈1,200 km from before 2026-09-01" in no_log["explanation"]
    m.log_event(session, action_code="FREEHUB_SERVICE", at="2026-08-15", component_id=wheel.id)
    ride(session, b, "2026-09-10", 795)
    st = status(session, wheel, "FREEHUB", date(2026, 10, 20))
    assert st["km_at_least"] and st["explanation"].startswith("at least 795 km since last service freehub")
    assert "inside the ≈1,200 km from before" in st["explanation"]
    m.log_event(session, action_code="FREEHUB_SERVICE", at="2026-09-20", component_id=wheel.id)
    assert not status(session, wheel, "FREEHUB", date(2026, 10, 20))["km_at_least"]


def test_time_reminders_count_from_install_not_purchase(session):
    """UAT B4: a new part bought before it was fitted is 'in use since' the install day."""
    b = bike(session)
    wheel = part(session, "FRONT_WHEEL", "New front", prior_usage="NEW", purchase_date="2026-08-20")
    inv.install(session, wheel.id, bike_id=b.id, at="2026-09-01")
    st = status(session, wheel, "FRONT_WHEEL_INSPECTION", date(2026, 10, 20))
    assert "in use since 2026-09-01" in st["explanation"]


def test_yearly_full_service_is_a_bike_reminder_with_a_checklist(session):
    b = bike(session)
    assert "Headset" in " ".join(ACTIONS["FULL_SERVICE"].checklist)
    row = bike_row(session, b, "BIKE_FULL_SERVICE", date(2026, 9, 1))
    assert row["status"] == "INSUFFICIENT_INFO" and row["component_id"] is None
    m.log_event(session, action_code="FULL_SERVICE", at="2026-03-01", bike_id=b.id,
                work_done="Done: Headset: clean, grease, check play.")
    row = bike_row(session, b, "BIKE_FULL_SERVICE", date(2026, 9, 1))
    assert row["status"] == "OK" and row["due_date"] == "2027-03-01"
    assert bike_row(session, b, "BIKE_FULL_SERVICE", date(2027, 2, 15))["status"] == "DUE_SOON"
    assert bike_row(session, b, "BIKE_FULL_SERVICE", date(2027, 3, 2))["status"] == "OVERDUE"


def test_tire_pressure_note_only_on_tires(session):
    b = bike(session)
    wheel = part(session, "FRONT_WHEEL", "DT Swiss front")
    inv.install(session, wheel.id, at="2026-09-01", bike_id=b.id)
    tire = part(session, "TIRE", "GP5000 front")
    inv.install(session, tire.id, at="2026-09-01", parent_component_id=wheel.id)
    inv.update_component(session, tire.id, pressure_note="  4.8 bar  ")
    assert tire.pressure_note == "4.8 bar"
    row = next(r for r in inv.bike_setup(session, b) if r["component_id"] == tire.id)
    assert row["pressure_note"] == "4.8 bar" and row["depth"] == 1      # shown on the bike page
    with pytest.raises(DomainError, match="goes on a tire"):
        inv.update_component(session, wheel.id, pressure_note="5 bar")
    with pytest.raises(DomainError, match="short"):
        inv.update_component(session, tire.id, pressure_note="x" * 81)
    inv.update_component(session, tire.id, pressure_note="")
    assert tire.pressure_note is None
