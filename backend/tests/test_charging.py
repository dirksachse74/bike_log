"""Dirk 2026-11-02: power-meter pedals with km from a previous bike; log each charge with a date and see the
riding (time and km) between charges. Plus Settings → Service intervals (/api/rules)."""
from fastapi.testclient import TestClient

from bikelog.api.app import create_app
from bikelog.db import make_session_factory
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m

from helpers import bike, part, ride


def test_charges_with_riding_between_them(session):
    b = bike(session)
    pedals = part(session, "POWER_METER_PEDALS", "Assioma Pro RS-1", prior_usage="RECORDED",
                  starting_km=3200, starting_date="2026-09-01")
    inv.install(session, pedals.id, bike_id=b.id, at="2026-09-01", slot="PEDALS")
    m.log_event(session, action_code="POWER_CHARGE", component_id=pedals.id, at="2026-09-01")
    ride(session, b, "2026-09-05", 80, duration_s=3 * 3600)
    ride(session, b, "2026-09-10", 60, duration_s=2 * 3600)
    m.log_event(session, action_code="POWER_CHARGE", component_id=pedals.id, at="2026-09-20")
    ride(session, b, "2026-09-25", 40, duration_s=5400)
    ride(session, b, "2026-09-26", 10)                       # no ride time
    h = m.charge_history(session, pedals)
    first, now = h["charges"][1], h["charges"][0]
    assert (first["charged_on"], first["until"], first["km"], first["hours"], first["rides"], first["days"]) == \
        ("2026-09-01", "2026-09-20", 140, 5, 2, 19)
    assert (now["until"], now["km"], now["hours"], now["rides"], now["rides_without_time"]) == (None, 50, 1.5, 2, 1)
    assert h["since_last"] == now and h["average"] == {"km": 140, "hours": 5, "days": 19, "charges": 1}
    assert m.charge_history(session, part(session, "SADDLE", "Arione")) is None
    di2 = part(session, "BATTERY", "BT-DN300")
    assert m.charge_history(session, di2) == {"charges": [], "since_last": None, "average": None}


def test_service_intervals_are_the_type_defaults_with_own_values_counted(session, engine, paths):
    pedals = part(session, "POWER_METER_PEDALS", "Assioma")
    m.set_component_rule(session, pedals.id, rule_code="POWER_PEDALS_CHARGE", interval_hours=60)
    session.commit()
    client = TestClient(create_app(make_session_factory(engine), paths, token="t", testing=True, static_dir=None))
    client.headers.update({"X-BikeLog-Token": "t"})
    rules = {r["rule_code"]: r for r in client.get("/api/rules").json()}
    assert rules["POWER_PEDALS_CHARGE"]["own_values"] == 1 and rules["POWER_PEDALS_CHARGE"]["interval_hours"] == 80
    assert rules["BRAKE_FLUID"]["interval_months"] == 24 and rules["CHAIN_HOT_WAX"]["after_top_up_km"] == 200
    r = client.patch(f"/api/rules/{rules['DI2_BATTERY_CHARGE']['id']}", json={"interval_km": 900, "warn_km": 100})
    assert r.status_code == 200 and r.json()["interval_km"] == 900 and r.json()["origin"] == "PERSONAL"
    detail = client.get(f"/api/components/{pedals.id}").json()
    assert detail["charging"] == {"charges": [], "since_last": None, "average": None}
