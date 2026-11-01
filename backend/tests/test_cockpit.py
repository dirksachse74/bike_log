"""Cockpit (bar and stem as one part) with its properties (Dirk 2026-11-01)."""
from test_api import client  # noqa: F401  (fixture)


def test_cockpit_type_with_properties_in_meta_add_and_edit(client):  # noqa: F811
    meta = client.get("/api/meta").json()
    cockpit = next(t for t in meta["component_types"] if t["code"] == "COCKPIT")
    assert cockpit["category"] == "Cockpit" and cockpit["torque"]
    keys = [f["key"] for f in cockpit["specs"]]
    assert keys[:6] == ["integration", "stem_length_mm", "stem_angle_deg", "reach_mm", "drop_mm", "width_mm"]
    assert next(f for f in cockpit["specs"] if f["key"] == "integration")["values"] == ["fully integrated", "semi integrated"]
    assert all(t["specs"] for t in meta["component_types"] if t["code"] != "OTHER")   # every part has properties

    bike = client.post("/api/bikes", json={"name": "Synapse"}).json()
    c = client.post("/api/components", json={
        "component_type": "COCKPIT", "label": "Vision Metron 5D", "prior_usage": "NEW",
        "specs": {"integration": "fully integrated", "stem_length_mm": 110, "stem_angle_deg": -10, "reach_mm": 80,
                  "drop_mm": 125, "width_mm": 400},
        "install": {"bike_id": bike["id"], "at": "2026-10-01"}}).json()
    detail = client.get(f"/api/components/{c['id']}").json()
    assert detail["specs"]["stem_length_mm"] == 110 and detail["location"]["state"] == "INSTALLED"
    r = client.patch(f"/api/components/{c['id']}", json={"specs": {**detail["specs"], "integration": "semi integrated"}})
    assert r.status_code == 200
    assert client.get(f"/api/components/{c['id']}").json()["specs"]["integration"] == "semi integrated"
    setup = client.get(f"/api/bikes/{bike['id']}").json()["setup"]
    assert any(r["slot"] == "COCKPIT" and r["label"] == "Vision Metron 5D" for r in setup)


def test_wheelset_rim_and_tire_size_properties(client):  # noqa: F811
    ws = next(t for t in client.get("/api/meta").json()["component_types"] if t["code"] == "WHEELSET")
    labels = [f["label"] for f in ws["specs"]]
    assert labels[:5] == ["Rim outer width", "Rim inner width", "Rim depth front", "Rim depth rear", "Tire size range"]
    c = client.post("/api/components", json={"component_type": "WHEELSET", "label": "Reserve 52|63", "prior_usage": "NEW",
                                             "notes": "Hookless", "specs": {"rim_outer_width_mm": 30, "internal_width_mm": 23.6,
                                                                            "rim_depth_front_mm": 52, "rim_depth_rear_mm": 63, "tire_size_range": "700x28c - 700x47c"}}).json()
    d = client.get(f"/api/components/{c['id']}").json()
    assert d["specs"]["internal_width_mm"] == 23.6 and d["specs"]["tire_size_range"] == "700x28c - 700x47c"
    assert d["notes"] == "Hookless" and (d["specs"]["rim_depth_front_mm"], d["specs"]["rim_depth_rear_mm"]) == (52, 63)
