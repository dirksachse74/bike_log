"""Frame and fork are parts (DECISIONS 96): every bike gets them automatically, they keep their own km,
a warranty frame starts at 0 km while the bike's total goes on, and a frame moved to a new build takes its
km along."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.models import Bike, Component, Installation
from bikelog.services.reference import ensure_reference_data
from bikelog.services import frames
from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services.errors import DomainError
from bikelog.services.usage import bike_usage

from helpers import bike, km, part, ride


def frame_of(session, b, ctype="FRAME"):
    return session.scalar(select(Component).join(Installation, Installation.component_id == Component.id)
                          .where(Installation.bike_id == b.id, Installation.removed_utc.is_(None),
                                 Component.component_type == ctype))


def test_new_bike_gets_frame_and_fork_that_count_every_ride(session):
    b = bike(session, purchase_date="2026-03-01")
    fr, fo = frame_of(session, b), frame_of(session, b, "FORK")
    assert fr.label == "TIME NXR frame" and fo.label == "TIME NXR fork"
    ride(session, b, "2026-04-01", 80)
    assert km(session, fr) == 80 and km(session, fo) == 80
    assert frames.ensure_frames(session) == 0                               # nothing twice


def test_existing_bike_gets_frame_with_starting_km_and_follows_older_rides(session):
    # a bike from before this change: no frame, starting km, rides
    b = Bike(name="BMC Roadmachine", status="ACTIVE", purchase_date="2026-05-01")
    session.add(b)
    session.flush()
    inv.set_starting_usage(session, bike_id=b.id, km=3000, effective="2026-05-01", is_estimate=True)
    assert frame_of(session, b) is None
    assert frames.ensure_frames(session) == 2                               # what the app does on start
    fr = frame_of(session, b)
    ride(session, b, "2026-05-10", 50)
    assert km(session, fr) == 3050
    ride(session, b, "2026-04-20", 30)                     # before the starting km: already inside them
    assert km(session, fr) == 3050 and bike_usage(session, b)["total_km"] == 3050
    # without starting km, an older ride arriving later (Strava, CSV) moves the automatic frame back
    b2 = bike(session, "Cube SL Road", purchase_date="2026-05-01")
    ride(session, b2, "2026-04-20", 30)
    assert km(session, frame_of(session, b2)) == 30 and km(session, frame_of(session, b2, "FORK")) == 30


def test_warranty_frame_starts_at_zero_and_bike_total_goes_on(session):
    b = bike(session, purchase_date="2026-03-01")
    ride(session, b, "2026-04-01", 500)
    old = frame_of(session, b)
    inv.update_component(session, old.id, serial_number="TN123", warranty_until="2031-03-01")
    res = inv.replace(session, old.id, at="2026-05-01", new={"label": "TIME NXR frame (warranty)"},
                      old_outcome="WARRANTY_RETURN", reason="crack at the seat cluster")
    ride(session, b, "2026-05-10", 100)
    new = inv.get_component(session, res["new_component_id"])
    assert km(session, new) == 100 and km(session, old) == 500
    assert old.disposition == "WARRANTY_RETURN" and old.serial_number == "TN123"
    assert bike_usage(session, b)["total_km"] == 600
    assert frames.ensure_frames(session) == 0                               # a real swap is never undone


def test_frame_moved_to_new_build_takes_its_km(session):
    b = bike(session, purchase_date="2026-03-01")
    ride(session, b, "2026-04-01", 1200)
    fr = frame_of(session, b)
    inv.remove(session, fr.id, at="2026-05-01", outcome="STORED")
    b2 = bike(session, "Winter build", purchase_date="2026-06-01")
    auto = frame_of(session, b2)
    inv.replace(session, auto.id, at="2026-06-02", new_component_id=fr.id, old_outcome="STORED")
    ride(session, b2, "2026-06-10", 40)
    assert km(session, fr) == 1240


def test_frame_history_lists_inspections_and_crashes_while_on_the_bike(session):
    b = bike(session, purchase_date="2026-03-01")
    r = ride(session, b, "2026-04-01", 60)
    inc.log(session, r.id, incident_type="CRASH", affected=["BIKE", "RIDER"])
    m.log_event(session, action_code="FRAME_INSPECT", at="2026-04-02", bike_id=b.id, outcome="OK")
    fr = frame_of(session, b)
    inv.replace(session, fr.id, at="2026-04-10", new={"label": "Second frame"}, old_outcome="WARRANTY_RETURN")
    m.log_event(session, action_code="FRAME_INSPECT", at="2026-04-20", bike_id=b.id, outcome="OK")
    old_h = frames.frame_history(session, fr)
    assert [e["performed_on"] for e in old_h["inspections"]] == ["2026-04-02"] and len(old_h["crashes"]) == 1
    new_h = frames.frame_history(session, frame_of(session, b))
    assert [e["performed_on"] for e in new_h["inspections"]] == ["2026-04-20"] and new_h["crashes"] == []


def test_warranty_date_is_checked(session):
    fr = frame_of(session, bike(session))
    with pytest.raises(DomainError, match="date"):
        inv.update_component(session, fr.id, warranty_until="next year")
    inv.update_component(session, fr.id, warranty_until="")
    assert fr.warranty_until is None


def test_empty_bike_with_its_automatic_frame_can_still_be_deleted(session):
    b = bike(session, "Typo bike")
    inv.delete_bike(session, b.id)
    session.flush()
    assert session.scalar(select(Component).where(Component.label.like("Typo bike%"))) is None


def test_warranty_over_http(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    c.headers.update({"X-BikeLog-Token": "t"})
    b = c.post("/api/bikes", json={"name": "TIME NXR"}).json()
    fr = next(p for p in c.get(f"/api/bikes/{b['id']}").json()["setup"] if p["component_type"] == "FRAME")
    r = c.patch(f"/api/components/{fr['component_id']}", json={"warranty_until": "2031-03-01"})
    assert r.status_code == 200, r.text
    d = c.get(f"/api/components/{fr['component_id']}").json()
    assert d["warranty_until"] == "2031-03-01" and d["frame_history"] == {"inspections": [], "crashes": []}
    assert c.patch(f"/api/components/{fr['component_id']}", json={"warranty_until": "soon"}).status_code in (400, 422)


def test_retiring_with_parts_off_keeps_frame_and_fork_on_the_bike(session):
    b = bike(session, purchase_date="2026-03-01")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2026-03-01", bike_id=b.id, slot="CHAIN")
    inv.retire_bike(session, b.id, parts_off_at="2026-03-01T12:00")
    assert inv.open_installation(session, chain.id) is None
    assert frame_of(session, b) is not None and frame_of(session, b, "FORK") is not None
