"""HTTP-level tests: the real app, real database, real services."""
import pytest
from fastapi.testclient import TestClient

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.services import demo
from bikelog.services.errors import Protected
from bikelog.services.reference import ensure_reference_data

TOKEN = "test-token"


@pytest.fixture()
def client(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    app = create_app(factory, paths, token=TOKEN, testing=True, static_dir=None)
    c = TestClient(app)
    c.headers.update({"X-BikeLog-Token": TOKEN})
    return c


def test_mutations_need_token_and_local_host(client):
    assert client.post("/api/bikes", json={"name": "x"}, headers={"X-BikeLog-Token": "wrong"}).status_code == 403
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/health").json()["ok"]


def test_main_workflow_over_http(client):
    bike = client.post("/api/bikes", json={"name": "TIME NXR"}).json()
    chain = client.post("/api/components", json={
        "component_type": "CHAIN", "label": "Chain A", "prior_usage": "NEW",
        "install": {"at": "2026-10-01", "bike_id": bike["id"]}}).json()
    assert chain["location"]["state"] == "INSTALLED"
    ev = client.post("/api/maintenance/events", json={"action_code": "WAX_HOT", "component_id": chain["id"],
                                                      "at": "2026-10-01"})
    assert ev.status_code == 201
    r = client.post("/api/rides", json={"bike_id": bike["id"], "when": "2026-10-02", "distance": 260},
                    headers={"X-Client-Op-Id": "add-1"})
    assert r.status_code == 201 and r.json()["change"]["notice"] == "Chain A +260.0 km."
    again = client.post("/api/rides", json={"bike_id": bike["id"], "when": "2026-10-02", "distance": 260},
                        headers={"X-Client-Op-Id": "add-1"}).json()
    assert again["repeated"] and again["result"]["id"] == r.json()["result"]["id"]
    q = client.get("/api/maintenance/queue").json()
    liquid = next(t for t in q if t["rule_code"] == "CHAIN_LIQUID_WAX")
    assert liquid["status"] == "DUE" and liquid["bike"] == "TIME NXR"
    ride_id = r.json()["result"]["id"]
    prev = client.patch(f"/api/rides/{ride_id}?dry_run=true", json={"distance_km": 200}).json()
    assert prev["change"]["preview"] and prev["change"]["deltas"][0]["delta_km"] == -60
    detail = client.get(f"/api/components/{chain['id']}").json()
    assert detail["usage"]["total_km"] == 260 and detail["ledger"][0]["km"] == 260
    assert any(s["rule_code"] == "CHAIN_HOT_WAX" for s in detail["service_status"])
    client.post(f"/api/rides/{ride_id}/exclude", json={"reason": "test"})
    assert client.get(f"/api/components/{chain['id']}").json()["usage"]["total_km"] == 0
    client.post(f"/api/rides/{ride_id}/restore")
    ov = client.get("/api/overview").json()
    assert ov["bikes"][0]["usage"]["total_km"] == 260 and ov["chains"][0]["state"] == "INSTALLED"


def test_errors_are_readable(client):
    bike = client.post("/api/bikes", json={"name": "TIME NXR"}).json()
    a = client.post("/api/components", json={"component_type": "CHAIN", "label": "A",
                                              "install": {"at": "2026-10-01", "bike_id": bike["id"]}}).json()
    b = client.post("/api/components", json={"component_type": "CHAIN", "label": "B"}).json()
    r = client.post(f"/api/components/{b['id']}/install", json={"at": "2026-10-05", "bike_id": bike["id"]})
    assert r.status_code == 409 and "occupied by A" in r.json()["detail"]
    assert client.post("/api/components", json={"component_type": "NOPE", "label": "x"}).status_code == 400
    assert client.get("/api/components/999").status_code == 404
    assert a


def test_csv_import_endpoint(client):
    client.post("/api/bikes", json={"name": "TIME NXR"})
    tmpl = client.get("/api/imports/template").text
    r = client.post("/api/imports/csv?file_name=t.csv", content=tmpl.encode(), headers={"content-type": "text/csv"})
    assert r.status_code == 200 and r.json()["counts"] == {"CREATED": 2}
    r = client.post("/api/imports/csv", content=tmpl.encode(), headers={"content-type": "text/csv"})
    assert r.json()["counts"] == {"UNCHANGED": 2}
    assert client.get("/api/strava/status").json()["live_connection_verified"] is False


def test_demo_data_never_goes_into_a_personal_database(engine):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
        with pytest.raises(Protected):
            demo.seed(s)
        from bikelog.services import inventory as inv
        inv.create_bike(s, name="My real bike")
    with session_scope(factory) as s:
        with pytest.raises(Protected):
            demo.mark_demo_database(s)


def test_demo_database_gets_sample_data(tmp_path):
    from bikelog.launcher import prepare
    from bikelog.paths import DataPaths
    paths = DataPaths(tmp_path / "demo").ensure()
    engine, factory, _ = prepare(paths, demo=True)
    with session_scope(factory) as s:
        from bikelog.services import maintenance as m
        chains = {c["label"]: c["state"] for c in m.chain_overview(s)}
        assert chains["Chain A"] == "INSTALLED" and chains["Chain B"] == "READY_TO_INSTALL"
        assert m.queue(s)
    prepare(paths, demo=True)   # second start: no duplicate sample data
    with session_scope(factory) as s:
        from sqlalchemy import func, select

        from bikelog.models import Bike
        assert s.scalar(select(func.count()).select_from(Bike)) == 2
    engine.dispose()


def test_replacement_from_stock_over_http_with_inventory_tabs_and_undo(client):
    bike = client.post("/api/bikes", json={"name": "TIME NXR"}).json()
    prod = client.post("/api/products", json={"component_type": "BRAKE_PADS", "maker": "Shimano",
                                               "model": "L05A-RF"}).json()
    old = client.post("/api/components", json={
        "component_type": "BRAKE_PADS", "label": "Rear pads", "prior_usage": "NEW", "product_id": prod["id"],
        "install": {"at": "2026-01-01", "bike_id": bike["id"], "slot": "REAR_PADS"}}).json()
    line = client.post("/api/consumables", json={"product_id": prod["id"], "storage_location": "Workshop drawer",
                                                 "min_stock": 3}).json()
    assert line["unit"] == "set"
    client.post(f"/api/consumables/{line['id']}/txn", json={"kind": "PURCHASE", "qty": 3, "on": "2026-02-01"})
    client.post(f"/api/products/{prod['id']}/compatibility", json={"bike_id": bike["id"], "verified": True})

    opts = client.get(f"/api/components/{old['id']}/replace-options").json()
    assert opts["suggested_outcome"] == "DISCARDED" and opts["location"]["slot"] == "REAR_PADS"
    assert opts["stock"][0]["id"] == line["id"] and opts["stock"][0]["fit"] == "VERIFIED"

    preview = client.post(f"/api/components/{old['id']}/replace?dry_run=true",
                          json={"at": "2026-03-02", "from_stock_id": line["id"], "old_outcome": "DISCARDED"}).json()
    assert preview["change"]["preview"]
    assert client.get("/api/inventory").json()["stock"][0]["stock"]["qty"] == 3   # preview saved nothing

    r = client.post(f"/api/components/{old['id']}/replace",
                    json={"at": "2026-03-02", "from_stock_id": line["id"], "old_outcome": "DISCARDED",
                          "reason": "worn"}, headers={"X-Client-Op-Id": "rep-1"}).json()
    again = client.post(f"/api/components/{old['id']}/replace",
                        json={"at": "2026-03-02", "from_stock_id": line["id"], "old_outcome": "DISCARDED",
                              "reason": "worn"}, headers={"X-Client-Op-Id": "rep-1"}).json()
    assert again["repeated"]                                           # retry does not use a second set
    view = client.get("/api/inventory").json()
    assert view["stock"][0]["stock"]["qty"] == 2 and view["stock"][0]["low"]
    assert view["shopping_list"][0]["suggested_qty"] == 1
    assert any(i["id"] == r["result"]["new_component_id"] for i in view["installed"])
    assert any(h["label"] == "Rear pads" and h["disposition"] == "DISCARDED" for h in view["history"])
    ws = client.get(f"/api/work-sessions/{r['result']['work_session_id']}").json()
    assert {t["kind"] for t in ws["transactions"]} >= {"STOCK_USE", "REMOVE", "INSTALL", "DISPOSITION"}

    undo = client.post(f"/api/work-sessions/{ws['id']}/undo", json={"reason": "test"})
    assert undo.status_code == 200
    view = client.get("/api/inventory").json()
    assert view["stock"][0]["stock"]["qty"] == 3
    detail = client.get(f"/api/components/{old['id']}").json()
    assert detail["location"]["state"] == "INSTALLED" and detail["disposition"] == "STORED"
