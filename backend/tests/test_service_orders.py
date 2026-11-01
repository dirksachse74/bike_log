"""Sending a part away for service or repair (DECISIONS 97): any part, four outcomes, cost counted once,
linked incident solved, the part's km stop while it is away, rides without a frame are flagged, undo."""
import pytest
from sqlalchemy import select

from bikelog.models import Component, Installation, RideFlag
from bikelog.services import costs
from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import service_orders as so
from bikelog.services import worksessions
from bikelog.services.errors import DomainError

from helpers import bike, km, part, ride


def on_bike(session, b, ctype):
    return session.scalar(select(Component).join(Installation, Installation.component_id == Component.id)
                          .where(Installation.bike_id == b.id, Installation.removed_utc.is_(None),
                                 Installation.voided_at.is_(None), Component.component_type == ctype))


def test_paid_frame_repair_after_a_crash(session):
    """Dirk's case: own mistake, frame sent away, repaired for 500 €."""
    b = bike(session, purchase_date="2026-03-01")
    frame = on_bike(session, b, "FRAME")
    r = ride(session, b, "2026-04-01", 100)
    inc.log(session, r.id, incident_type="CRASH", affected=[f"c{frame.id}"])
    group = inc.all_incidents(session, bike_id=b.id)[0]["group"]
    assert any(c["group"] == group for c in so.incident_choices(session, frame))
    res = so.send_out(session, frame.id, at="2026-04-02T18:00", shop="Carbon repair shop", reason="crack at the top tube",
                      incident_group=group)
    assert inv.location(session, frame)["text"] == "Away for repair at Carbon repair shop since 2026-04-02"
    assert [o["id"] for o in so.away(session, b.id)] == [res["order_id"]]
    # a ride while the frame is away: flagged, and the frame gets no km
    r2 = ride(session, b, "2026-04-10", 30)
    assert "NO_FRAME" in {f.code for f in session.scalars(select(RideFlag).where(RideFlag.ride_id == r2.id))}
    assert km(session, frame) == 100
    with pytest.raises(DomainError, match="later"):
        so.return_part(session, res["order_id"], at="2026-04-01", outcome="REPAIRED_PAID")
    back = so.return_part(session, res["order_id"], at="2026-04-20", outcome="REPAIRED_PAID", cost_cents=50000,
                          receipt_ref="INV-2026-117", notes="top tube re-wrapped")
    assert back["placed"] == "back on" and back["incident_solved"] is True
    ride(session, b, "2026-04-21", 40)
    assert km(session, frame) == 140 and frame.disposition == "STORED"
    service = [i for i in costs.bike_costs(session, b)["items"] if i["kind"] == "SERVICE"]
    assert [i["cents"] for i in service] == [50000]
    row = so.for_component(session, frame)[0]
    assert row["outcome_text"] == "Repaired (paid)" and row["shop"] == "Carbon repair shop"
    assert row["incident"]["open"] is False
    entry = inc.all_incidents(session, bike_id=b.id)[0]["affected"][0]
    assert entry["repair"] == "REPAIRED" and "500.00" in entry["repair_text"]


def test_warranty_replacement_brings_a_new_frame_at_zero_km(session):
    b = bike(session, purchase_date="2026-03-01")
    ride(session, b, "2026-04-01", 800)
    old = on_bike(session, b, "FRAME")
    o = so.send_out(session, old.id, at="2026-04-02T18:00", shop="TIME")["order_id"]
    res = so.return_part(session, o, at="2026-05-01", outcome="REPLACED_WARRANTY", new_label="NXR frame #2",
                         new_serial="TN999", new_warranty_until="2031-05-01")
    new = inv.get_component(session, res["replacement_id"])
    ride(session, b, "2026-05-02", 50)
    assert km(session, new) == 50 and km(session, old) == 800
    assert old.disposition == "WARRANTY_RETURN" and new.serial_number == "TN999" and new.warranty_until == "2031-05-01"
    assert on_bike(session, b, "FRAME").id == new.id
    assert so.for_component(session, new)[0]["outcome"] == "REPLACED_WARRANTY"     # the new frame knows why


def test_wheel_sent_away_while_a_spare_rides_then_comes_back(session):
    b = bike(session, purchase_date="2026-03-01")
    wheel = part(session, "REAR_WHEEL", "Reynolds rear")
    spare = part(session, "REAR_WHEEL", "Winter rear")
    inv.install(session, wheel.id, at="2026-03-01", bike_id=b.id, slot="REAR_WHEEL")
    o = so.send_out(session, wheel.id, at="2026-04-01T20:00", shop="Wheel builder", reason="hub noise")["order_id"]
    inv.install(session, spare.id, at="2026-04-02", bike_id=b.id, slot="REAR_WHEEL")
    ride(session, b, "2026-04-05", 60)
    back = so.return_part(session, o, at="2026-04-10", outcome="REPAIRED_WARRANTY")
    ride(session, b, "2026-04-12", 20)
    assert km(session, spare) == 60 and km(session, wheel) == 20
    assert back["placed"].startswith("back on, Winter rear stored")
    assert [i for i in costs.bike_costs(session, b)["items"] if i["kind"] == "SERVICE"] == []


def test_not_repaired_part_comes_back_stored_or_discarded(session):
    b = bike(session)
    rd = part(session, "REAR_DERAILLEUR", "Ultegra Di2 RD")
    inv.install(session, rd.id, at="2026-03-01", bike_id=b.id, slot="REAR_DERAILLEUR")
    o = so.send_out(session, rd.id, at="2026-04-01T20:00", shop="Shimano service")["order_id"]
    so.return_part(session, o, at="2026-04-20", outcome="NOT_REPAIRED", keep_as="DISCARDED", cost_cents=2500)
    assert rd.disposition == "DISCARDED" and inv.open_installation(session, rd.id) is None


def test_undo_return_and_send(session):
    b = bike(session, purchase_date="2026-03-01")
    frame = on_bike(session, b, "FRAME")
    res = so.send_out(session, frame.id, at="2026-04-01T20:00", shop="Shop")
    back = so.return_part(session, res["order_id"], at="2026-04-10", outcome="REPAIRED_PAID", cost_cents=100)
    worksessions.undo(session, back["work_session_id"], "typo")
    assert so.away(session, b.id)[0]["status"] == "OUT" and inv.open_installation(session, frame.id) is None
    worksessions.undo(session, res["work_session_id"], "never sent")
    assert so.away(session, b.id) == [] and inv.open_installation(session, frame.id) is not None
    assert so.for_component(session, frame) == []


def test_cannot_send_twice(session):
    b = bike(session, purchase_date="2026-03-01")
    frame = on_bike(session, b, "FRAME")
    so.send_out(session, frame.id, at="2026-04-01T20:00")
    with pytest.raises(DomainError, match="already away"):
        so.send_out(session, frame.id, at="2026-04-02T20:00")


def test_send_out_and_return_over_http(engine, paths):
    from fastapi.testclient import TestClient

    from bikelog.api.app import create_app
    from bikelog.db import make_session_factory, session_scope
    from bikelog.services.reference import ensure_reference_data
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    c.headers.update({"X-BikeLog-Token": "t"})
    b = c.post("/api/bikes", json={"name": "TIME NXR", "purchase_date": "2026-03-01"}).json()
    frame = next(p for p in c.get(f"/api/bikes/{b['id']}").json()["setup"] if p["component_type"] == "FRAME")
    r = c.post(f"/api/components/{frame['component_id']}/send-out", json={"at": "2026-04-01T20:00", "shop": "Shop"})
    assert r.status_code == 200, r.text
    away = c.get(f"/api/bikes/{b['id']}").json()["away"]
    assert len(away) == 1 and away[0]["shop"] == "Shop"
    r = c.post(f"/api/service-orders/{away[0]['id']}/return", json={"at": "2026-04-10", "outcome": "REPAIRED_PAID",
                                                                    "cost_cents": 50000})
    assert r.status_code == 200, r.text
    d = c.get(f"/api/components/{frame['component_id']}").json()
    assert d["service_orders"][0]["outcome"] == "REPAIRED_PAID" and d["location"]["state"] == "INSTALLED"
    assert c.post(f"/api/service-orders/{away[0]['id']}/return", json={"at": "2026-04-11", "outcome": "REPAIRED_PAID"}).status_code in (400, 409, 422)
