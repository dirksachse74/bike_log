"""Pick lists (DECISIONS 106): shop names offered in dropdowns, managed in Settings → Lists."""
import pytest
from fastapi.testclient import TestClient

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.services.reference import ensure_reference_data


@pytest.fixture()
def c(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    client = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    client.headers.update({"X-BikeLog-Token": "t"})
    return client


def test_shop_on_part_bike_and_purchase_goes_on_the_list(c):
    r = c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain A", "shop": " bike-components.de "})
    assert r.status_code == 201 and r.json()["shop"] == "bike-components.de"
    # another spelling of the same shop is stored as the list's name
    r = c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain B", "shop": "Bike-Components.DE"})
    assert r.json()["shop"] == "bike-components.de"
    b = c.post("/api/bikes", json={"name": "TIME NXR", "shop": "Local shop"}).json()
    assert b["shop"] == "Local shop"
    assert c.get("/api/lists/SHOP").json() == ["bike-components.de", "Local shop"]
    lists = c.get("/api/lists").json()
    shops = {i["name"]: i for i in lists[0]["items"]}
    assert lists[0]["code"] == "SHOP" and shops["bike-components.de"]["uses"] == 2


def test_rename_merge_and_hide(c):
    a = c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain A", "shop": "BC"}).json()
    d = c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain B", "shop": "Bike Comp"}).json()
    items = {i["name"]: i["id"] for i in c.get("/api/lists").json()[0]["items"]}
    # rename: the parts follow, and the change log records it
    r = c.patch(f"/api/lists/items/{items['BC']}", json={"name": "bike-components.de"})
    assert r.status_code == 200 and r.json()["uses"] == 1
    assert c.get(f"/api/components/{a['id']}").json()["shop"] == "bike-components.de"
    log = c.get("/api/changes", params={"component_id": a["id"]}).json()
    assert any(r["field"] == "shop" and r["old_value"] == "BC" and r["new_value"] == "bike-components.de" for r in log)
    # renaming onto an existing name is refused: that is a merge
    assert c.patch(f"/api/lists/items/{items['Bike Comp']}", json={"name": "BIKE-components.de"}).status_code == 409
    r = c.post(f"/api/lists/items/{items['Bike Comp']}/merge", json={"into_id": items["BC"]})
    assert r.status_code == 200 and r.json()["moved"] == 1 and r.json()["uses"] == 2
    assert c.get(f"/api/components/{d['id']}").json()["shop"] == "bike-components.de"
    assert c.get("/api/lists/SHOP").json() == ["bike-components.de"]
    # typing the merged name again gives the kept one
    e = c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain C", "shop": "bike comp"}).json()
    assert e["shop"] == "bike-components.de"
    # hide: out of the dropdown, records keep it; using it again brings it back
    c.patch(f"/api/lists/items/{items['BC']}", json={"hidden": True})
    assert c.get("/api/lists/SHOP").json() == []
    assert c.get(f"/api/components/{a['id']}").json()["shop"] == "bike-components.de"
    c.post("/api/lists/SHOP", json={"name": "Rose"})
    assert c.post("/api/lists/SHOP", json={"name": "rose"}).status_code == 409
    c.patch(f"/api/components/{a['id']}", json={"shop": "bike-components.de"})
    assert c.get("/api/lists/SHOP").json() == ["bike-components.de", "Rose"]


def test_work_done_by_a_bike_shop(c):
    """Dirk 2026-11-01: Record work done can name the bike shop that did it (same shop list)."""
    c.post("/api/components", json={"component_type": "CHAIN", "label": "Chain A", "shop": "Velo Haus"})
    b = c.post("/api/bikes", json={"name": "Synapse"}).json()
    r = c.post("/api/maintenance/events", json={"action_code": "FRAME_INSPECT", "at": "2026-10-01", "bike_id": b["id"],
                                                "cost_cents": 8900, "shop": "velo haus"})
    assert r.status_code == 201, r.text
    ev_id = r.json()["event_ids"][0]
    ev = next(e for e in c.get("/api/maintenance/events", params={"bike_id": b["id"]}).json() if e["id"] == ev_id)
    assert ev["shop"] == "Velo Haus"                       # the list's spelling
    costs = c.get(f"/api/bikes/{b['id']}").json()["cost_detail"]
    assert any(i["kind"] == "SERVICE" and "(Velo Haus)" in i["text"] for i in costs["items"])
    # a new shop typed there goes on the list; the entry can be corrected
    assert c.patch(f"/api/maintenance/events/{ev_id}", json={"shop": "Radhaus Mitte"}).status_code == 200
    assert "Radhaus Mitte" in c.get("/api/lists/SHOP").json()
    items = {i["name"]: i for i in c.get("/api/lists").json()[0]["items"]}
    assert items["Radhaus Mitte"]["uses"] == 1
