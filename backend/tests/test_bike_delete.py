"""Delete a bike created by mistake; retire (and restore) a bike with history; a deleted Strava bike stays gone."""
import pytest
from fastapi.testclient import TestClient

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.models import Bike
from bikelog.services import inventory as inv
from bikelog.services import settings
from bikelog.services.errors import Protected

from bikelog.services.reference import ensure_reference_data

from helpers import bike, km, part, ride


@pytest.fixture()
def client(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None), raise_server_exceptions=False)
    c.headers.update({"X-BikeLog-Token": "t"})
    return c


def test_bike_without_history_can_be_deleted_and_its_strava_gear_is_ignored(session):
    b = bike(session, "Typo bike")
    b.strava_gear_id = "123"
    inv.set_starting_usage(session, bike_id=b.id, km=100, effective="2026-10-01", is_estimate=True)
    assert inv.delete_bike(session, b.id) == "Typo bike"
    assert session.get(Bike, b.id) is None
    assert "123" in settings.get(session, "strava_ignored_gear")


def test_bike_with_history_is_retired_not_deleted_and_can_come_back(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2026-10-01", bike_id=b.id, slot="CHAIN")
    ride(session, b, "2026-10-02", 50)
    with pytest.raises(Protected, match="Retire it instead"):
        inv.delete_bike(session, b.id)
    inv.retire_bike(session, b.id, parts_off_at="2026-10-05")
    assert b.status == "RETIRED" and inv.open_installation(session, chain.id) is None
    assert km(session, chain) == 50 and chain.disposition == "STORED" and chain.rotation_bike_id is None
    inv.restore_bike(session, b.id)
    assert b.status == "ACTIVE"


def test_delete_and_retire_over_http(client):
    b = client.post("/api/bikes", json={"name": "Mistake"}).json()
    assert client.get(f"/api/bikes/{b['id']}").json()["history_counts"]["rides"] == 0
    assert client.delete(f"/api/bikes/{b['id']}").json()["name"] == "Mistake"
    assert client.get(f"/api/bikes/{b['id']}").status_code == 404
    assert client.get("/api/changes", params={"bike_id": b["id"]}).json()[0]["action"] == "DELETED"
    b2 = client.post("/api/bikes", json={"name": "Old bike"}).json()
    assert client.post(f"/api/bikes/{b2['id']}/retire").json()["status"] == "RETIRED"
    assert client.post(f"/api/bikes/{b2['id']}/restore").json()["status"] == "ACTIVE"
