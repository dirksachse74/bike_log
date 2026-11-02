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


def test_bike_with_history_deleted_for_good_parts_keep_their_km(session):
    """Dirk 2026-11-02: delete a bike for good. It and its rides are shown nowhere any more, imported rides are
    not imported again, its parts go to storage with the km they did on it."""
    from bikelog.models import Ride
    from bikelog.services import bike_purge, incidents as inc, rides as rides_svc
    from bikelog.services.errors import DomainError
    keep = bike(session, "Synapse")
    b = bike(session, "Old bike")
    b.strava_gear_id = "b77"
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2026-09-01", bike_id=b.id, slot="CHAIN")
    r1 = ride(session, b, "2026-09-02", 50)
    imported = ride(session, b, "2026-09-03", 30)
    imported.source_kind = "STRAVA"
    other = ride(session, keep, "2026-09-03", 70)
    inc.log(session, r1.id, incident_type="FLAT",
            affected=[o["key"] for o in inc.choices(session, r1, "FLAT")][:1])
    assert km(session, chain) == 80 and len(inc.all_incidents(session)) == 1
    pv = bike_purge.preview(session, b.id)
    assert pv["rides"] == 2 and pv["parts"][0]["km_on_bike"] == 80
    with pytest.raises(DomainError, match="Type the bike"):
        bike_purge.purge(session, b.id, confirm_name="wrong")
    res = bike_purge.purge(session, b.id, confirm_name="old bike")
    assert res["rides"] == 2 and res["parts"] == 2          # the chain and the bike's frame
    gone = session.get(Bike, b.id)
    assert gone.deleted_at and gone.name.startswith("Old bike (deleted ") and gone.strava_gear_id is None
    assert "b77" in settings.get(session, "strava_ignored_gear")
    assert km(session, chain) == 80 and inv.get_component(session, chain.id).disposition == "STORED"
    assert session.get(Ride, imported.id).inclusion == "EXCLUDED"
    assert [r["id"] for r in rides_svc.list_rides(session, limit=50)] == [other.id]       # in no ride list
    assert inc.all_incidents(session) == []
    assert inv.create_bike(session, name="Old bike").name == "Old bike"                # the name is free again


def test_purge_over_http_needs_the_name_and_hides_retired_bikes_on_the_overview(client):
    a = client.post("/api/bikes", json={"name": "Keep"}).json()
    r = client.post("/api/bikes", json={"name": "Gone"}).json()
    client.post("/api/rides", json={"bike_id": r["id"], "when": "2026-10-02", "distance": 20})
    assert client.post(f"/api/bikes/{r['id']}/purge", json={"confirm_name": "nope"}).status_code == 400
    assert client.get(f"/api/bikes/{r['id']}/purge-preview").json()["rides"] == 1
    res = client.post(f"/api/bikes/{r['id']}/purge", json={"confirm_name": "Gone", "retire_parts": True})
    assert res.status_code == 200 and res.json()["name"] == "Gone"
    assert [b["name"] for b in client.get("/api/bikes").json()] == ["Keep"]
    assert client.get("/api/rides").json() == []
    client.post(f"/api/bikes/{a['id']}/retire", json={})
    assert client.get("/api/overview").json()["bikes"] == []
