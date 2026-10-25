"""Time-based reminders (brake fluid, sealant), tube/tubeless setup on wheels, the change log,
the diagnostic log on the Settings page, and the headset / power-meter part types."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from bikelog.api.app import create_app
from bikelog.changelog import change_source, entries
from bikelog.db import make_session_factory, session_scope
from bikelog.models import ChangeLog
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services.errors import DomainError
from bikelog.services.reference import ensure_reference_data

from helpers import bike, part

TOKEN = "test-token"


def status(session, comp, code, today):
    return next(r for r in m.component_status(session, comp, today) if r["rule_code"] == code)


def in_queue(session, comp, code, today):
    return any(r["component_id"] == comp.id and r["rule_code"] == code for r in m.queue(session, today=today))


def test_brake_fluid_time_reminder_end_to_end(session):
    b = bike(session)
    front = part(session, "BRAKE_CIRCUIT", "Front brake", prior_usage="UNKNOWN")
    inv.install(session, front.id, bike_id=b.id, slot="FRONT_BRAKE", at="2024-01-01")
    assert status(session, front, "BRAKE_FLUID", date(2026, 10, 25))["status"] == "INSUFFICIENT_INFO"
    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=front.id, at="2024-11-01")
    soon = status(session, front, "BRAKE_FLUID", date(2026, 10, 25))
    assert soon["status"] == "DUE_SOON" and soon["due_date"] == "2026-11-01" and soon["days_left"] == 7
    assert in_queue(session, front, "BRAKE_FLUID", date(2026, 10, 25))
    m.log_event(session, action_code="BRAKE_BLEED", component_id=front.id, at="2026-10-20")   # no reset
    late = status(session, front, "BRAKE_FLUID", date(2026, 11, 10))
    assert late["status"] == "OVERDUE" and "bleed" in late["explanation"]
    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=front.id, at="2026-11-10")
    assert status(session, front, "BRAKE_FLUID", date(2026, 11, 10))["due_date"] == "2028-11-10"


def test_sealant_reminder_only_for_tubeless_and_setup_moves_with_the_wheel(session):
    b1, b2 = bike(session, "BMC Roadmachine"), bike(session, "TIME NXR")
    wheel = part(session, "REAR_WHEEL", "Zipp 303 rear")
    tire = part(session, "TIRE", "GP5000 S TR rear")
    inv.install(session, wheel.id, bike_id=b1.id, at="2026-05-01")
    inv.install(session, tire.id, parent_component_id=wheel.id, at="2026-05-01")
    today = date(2026, 8, 25)
    st = status(session, tire, "TIRE_SEALANT", today)
    assert st["status"] == "NOT_APPLICABLE" and "not set on Zipp 303 rear" in st["explanation"]
    assert not in_queue(session, tire, "TIRE_SEALANT", today)
    with pytest.raises(DomainError):
        inv.update_component(session, tire.id, tire_setup="TUBELESS")   # set on the wheel, not the tire
    with pytest.raises(DomainError):
        inv.update_component(session, wheel.id, tire_setup="SLIME")
    inv.update_component(session, wheel.id, tire_setup="TUBELESS")
    assert inv.tire_setup_of(session, tire) == ("TUBELESS", wheel)
    m.log_event(session, action_code="SEALANT_TOP_UP", component_id=tire.id, at="2026-06-01")
    st = status(session, tire, "TIRE_SEALANT", today)
    assert st["status"] == "DUE_SOON" and st["due_date"] == "2026-09-01"
    assert in_queue(session, tire, "TIRE_SEALANT", today)
    m.log_event(session, action_code="SEALANT_RENEW", component_id=tire.id, at="2026-08-20")
    assert status(session, tire, "TIRE_SEALANT", today)["due_date"] == "2026-11-20"
    # wheelset swap: the wheel (with its tire) moves to the other bike and stays tubeless
    inv.move(session, wheel.id, at="2026-08-21", bike_id=b2.id, slot="REAR_WHEEL")
    assert inv.tire_setup_of(session, tire)[0] == "TUBELESS"
    assert status(session, tire, "TIRE_SEALANT", today)["status"] == "OK"
    inv.update_component(session, wheel.id, tire_setup="TUBE")
    assert status(session, tire, "TIRE_SEALANT", today)["status"] == "NOT_APPLICABLE"
    # the interval is configurable per part (months), like every rule
    inv.update_component(session, wheel.id, tire_setup="TUBELESS")
    m.set_component_rule(session, tire.id, rule_code="TIRE_SEALANT", interval_months=6)
    assert status(session, tire, "TIRE_SEALANT", today)["due_date"] == "2027-02-20"
    with pytest.raises(IntegrityError, match="INVALID"):
        session.execute(text("UPDATE component SET tire_setup = 'FOAM' WHERE id = :i"), {"i": wheel.id})


def test_change_log_records_old_and_new_values_and_installations(session):
    b = bike(session, "Cube SL Road SL")
    inv.update_bike(session, b.id, name="Cube SL Road", purchase_price_cents=149900)
    chain = part(session, "CHAIN", "Chain A", price_cents=3999)
    inv.update_component(session, chain.id, label="Chain A (KMC)", price_cents=4499, specs={"links": 116})
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    inv.remove(session, chain.id, at="2026-10-10", outcome="STORED")
    session.flush()
    rows = entries(session, component_id=chain.id)
    got = {(r["action"], r["field"], r["old_value"], r["new_value"]) for r in rows}
    assert ("CHANGED", "label", "Chain A", "Chain A (KMC)") in got
    assert ("CHANGED", "price", "€39.99", "€44.99") in got
    assert ("CHANGED", "spec: links", None, "116") in got
    assert any(a == "INSTALLED" and "Cube SL Road (chain) from 2026-10-01" in n for a, _, _, n in got)
    assert any(a == "REMOVED" and "on 2026-10-10" in n for a, _, _, n in got)
    assert any(a == "CREATED" for a, *_ in got) and all(r["who"] == "You (app)" for r in rows)
    bike_rows = {(r["action"], r["field"], r["old_value"], r["new_value"]) for r in entries(session, bike_id=b.id)}
    assert ("CHANGED", "name", "Cube SL Road SL", "Cube SL Road") in bike_rows
    assert ("CHANGED", "purchase price", None, "€1,499.00") in bike_rows
    assert any(a == "INSTALLED" for a, *_ in bike_rows)        # parts installed on the bike show there too
    with change_source("STRAVA"):
        inv.update_bike(session, b.id, strava_gear_id="b123")
    session.flush()
    assert entries(session, bike_id=b.id)[0]["who"] == "Strava sync"
    session.commit()
    with pytest.raises(IntegrityError, match="PROTECTED"):
        session.execute(text("DELETE FROM change_log"))
    session.rollback()
    with pytest.raises(IntegrityError, match="PROTECTED"):
        session.execute(text("UPDATE change_log SET new_value = 'x'"))
    session.rollback()


def test_typo_part_can_still_be_deleted_and_keeps_its_log(session):
    typo = part(session, "CHAIN", "Chian B")
    inv.delete_component(session, typo.id)
    actions = [r["action"] for r in entries(session, component_id=typo.id)]
    assert actions == ["DELETED", "CREATED"]


@pytest.fixture()
def client(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token=TOKEN, testing=True, static_dir=None),
                   raise_server_exceptions=False)
    c.headers.update({"X-BikeLog-Token": TOKEN})
    c.factory = factory
    return c


def test_change_log_over_http_names_the_operation_and_dry_runs_leave_no_trace(client):
    b = client.post("/api/bikes", json={"name": "TIME NXR"}).json()
    chain = client.post("/api/components", json={"component_type": "CHAIN", "label": "Chain A"}).json()
    r = client.post(f"/api/components/{chain['id']}/install?dry_run=true", json={"at": "2026-10-01", "bike_id": b["id"]})
    assert r.status_code == 200
    assert [x["action"] for x in client.get(f"/api/changes?component_id={chain['id']}").json()] == ["CREATED"]
    client.post(f"/api/components/{chain['id']}/install", json={"at": "2026-10-01", "bike_id": b["id"]})
    top = client.get(f"/api/changes?component_id={chain['id']}").json()[0]
    assert top["action"] == "INSTALLED" and top["via"] == "component.install" and top["who"] == "You (app)"
    wheel = client.post("/api/components", json={"component_type": "FRONT_WHEEL", "label": "Front wheel",
                                                 "tire_setup": "TUBELESS"}).json()
    assert wheel["tire_setup"] == "TUBELESS"
    r = client.patch(f"/api/components/{wheel['id']}", json={"tire_setup": "TUBE"}).json()
    assert r["tire_setup"] == "TUBE"
    top = client.get(f"/api/changes?component_id={wheel['id']}").json()[0]
    assert (top["field"], top["old_value"], top["new_value"]) == ("tire setup", "tubeless (sealant)", "inner tube")
    assert client.get("/api/changes").status_code == 400
    assert {t["code"] for t in client.get("/api/meta").json()["tire_setups"]} == {"TUBE", "TUBELESS", "TUBULAR"}


def test_logs_are_readable_from_settings_and_never_show_secrets(client, paths):
    import logging

    from bikelog.logging_setup import setup_logging
    setup_logging(paths.logs, console=False)
    try:
        logging.getLogger("bikelog.test").info("client_secret=abcdef0123456789abcdef0123456789abcdef01 saved")
        client.post("/api/bikes", json={"name": "BMC Roadmachine"})
        client.post("/api/components", json={"component_type": "CHAIN", "label": ""})   # refused → logged
        # a line written by an older version, before redaction existed, is still redacted on the way out
        with (paths.logs / "bikelog.log").open("a", encoding="utf-8") as f:
            f.write("2026-10-25 10:00:00,000 INFO    old: refresh_token=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz\n")
        out = client.get("/api/logs?lines=50").json()
        text_all = "\n".join(out["lines"])
        assert "abcdef0123456789" not in text_all and "zzzzzzzz" not in text_all and "[REDACTED]" in text_all
        assert "refused POST /api/components" in text_all
        assert out["file"].endswith("bikelog.log")
        warn = client.get("/api/logs?level=warning").json()["lines"]
        assert not any(" INFO " in line for line in warn)
        dl = client.get("/api/logs/download")
        assert dl.status_code == 200 and "zzzzzzzz" not in dl.text and "attachment" in dl.headers["content-disposition"]
    finally:
        for h in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(h)
            h.close()


def test_headset_and_power_meter_types(session):
    b = bike(session)
    crank = part(session, "CRANKSET", "Ultegra crank")
    pm = part(session, "POWER_METER", "4iiii Precision 3+")
    headset = part(session, "HEADSET", "Cane Creek 40")
    inv.install(session, crank.id, bike_id=b.id, at="2026-01-01")
    inv.install(session, pm.id, parent_component_id=crank.id, at="2026-01-01")      # on the crank (or on the bike)
    inv.install(session, headset.id, bike_id=b.id, at="2026-01-01")
    assert inv.location(session, pm)["text"].startswith("TIME NXR → Ultegra crank")
    st = status(session, headset, "HEADSET_SERVICE", date(2026, 12, 15))
    assert st["status"] == "DUE_SOON" and st["due_date"] == "2027-01-01"
    m.log_event(session, action_code="POWER_ZERO_OFFSET", component_id=pm.id, at="2026-02-01")
    with pytest.raises(DomainError):
        m.log_event(session, action_code="POWER_BATTERY", component_id=headset.id, at="2026-02-01")
    assert session.scalars(select(ChangeLog).where(ChangeLog.component_id == pm.id)).first() is not None
