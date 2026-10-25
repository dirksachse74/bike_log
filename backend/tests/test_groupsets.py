"""Groupset import: a whole Ultegra Di2 R8100 group in one action, placed, undoable, no duplicates."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.models import Component, Installation, Product
from bikelog.services import groupsets as gs
from bikelog.services import inventory as inv
from bikelog.services import worksessions as ws_svc
from bikelog.services.errors import DomainError
from bikelog.services.reference import ensure_reference_data

from helpers import bike, km, part, ride

R8100 = "SHIMANO_ULTEGRA_DI2_R8100"


def wheels(session, b):
    front = part(session, "FRONT_WHEEL", "Front wheel")
    rear = part(session, "REAR_WHEEL", "Rear wheel")
    inv.install(session, front.id, bike_id=b.id, at="2026-08-01")
    inv.install(session, rear.id, bike_id=b.id, at="2026-08-01")
    return front, rear


def run_import(session, b=None, **kw):
    ws = ws_svc.begin(session, at=kw.get("at", "2026-10-25"), bike_id=b.id if b else None, title="Groupset")
    kw.setdefault("at", "2026-10-25")
    return gs.import_groupset(session, R8100, bike_id=b.id if b else None, work_session_id=ws.id, **kw)


def by_key(result):
    return {r["key"]: r for r in result["items"]}


def test_shipped_templates_are_consistent():
    assert gs.check_templates() == []


def test_whole_groupset_installed_on_bike_with_wheels(session):
    b = bike(session)
    front, rear = wheels(session, b)
    res = run_import(session, b, options={"gearing": "50-34", "crank_length": "170", "cassette": "11-30"})
    rows = by_key(res)
    assert res["counts"] == {"INSTALL": 19, "REPLACE": 0, "SPARE": 0}   # every default part (incl. 2 pulley wheels), wires left out
    assert "wires" not in rows
    setup = {(r["slot"], r["label"]) for r in inv.bike_setup(session, b)}
    assert ("CRANKSET", "Ultegra crankset") in setup
    assert ("CHAINRING_OUTER", "Ultegra outer chainring 50T") in setup
    assert ("QUICK_LINK", "Ultegra quick link") in setup
    # mounted on the right parents
    cassette = inv.get_component(session, rows["cassette"]["component_id"])
    assert inv.open_installation(session, cassette.id).parent_component_id == rear.id
    rotor_f = inv.open_installation(session, rows["rotor_front"]["component_id"])
    assert rotor_f.parent_component_id == front.id and rotor_f.slot == "ROTOR"
    ring = inv.open_installation(session, rows["chainring_inner"]["component_id"])
    assert ring.parent_component_id == rows["crankset"]["component_id"]
    # products carry the chosen options and the unverified source
    crank = session.get(Product, cassette.product_id)
    assert crank.model == "CS-R8100-12 11-30"
    assert "not verified" in (crank.notes or "")
    # both pad sets share one product
    pads = {inv.get_component(session, rows[k]["component_id"]).product_id for k in ("pads_front", "pads_rear")}
    assert len(pads) == 1
    # new parts count rides from the install date on
    ride(session, b, "2026-10-26", 80)
    assert km(session, inv.get_component(session, rows["chain"]["component_id"])) == 80
    assert km(session, cassette) == 80


def test_occupied_positions_kept_by_default_and_wheel_parts_without_wheels_become_spares(session):
    b = bike(session)
    old_chain = part(session, "CHAIN", "Chain A")
    inv.install(session, old_chain.id, bike_id=b.id, at="2026-08-01")
    res = run_import(session, b)
    rows = by_key(res)
    assert rows["chain"]["action"] == "SPARE" and "Chain A" in rows["chain"]["text"]
    assert inv.open_installation(session, old_chain.id) is not None
    # the quick link still goes on the new (spare) chain
    assert inv.open_installation(session, rows["quick_link"]["component_id"]).parent_component_id == \
        rows["chain"]["component_id"]
    for k in ("cassette", "rotor_front", "rotor_rear"):
        assert rows[k]["action"] == "SPARE"
        assert inv.open_installation(session, rows[k]["component_id"]) is None


def test_replace_mode_replaces_old_parts_and_records_their_outcome(session):
    b = bike(session)
    _, rear = wheels(session, b)
    old_chain = part(session, "CHAIN", "Chain A")
    old_cassette = part(session, "CASSETTE", "Old 11s cassette")
    old_pads = part(session, "BRAKE_PADS", "Old front pads")
    inv.install(session, old_chain.id, bike_id=b.id, at="2026-08-01")
    inv.install(session, old_cassette.id, parent_component_id=rear.id, at="2026-08-01")
    inv.install(session, old_pads.id, bike_id=b.id, slot="FRONT_PADS", at="2026-08-01")
    ride(session, b, "2026-09-01", 300)
    res = run_import(session, b, occupied="REPLACE", outcomes={"chain": "SOLD"})
    rows = by_key(res)
    assert rows["chain"]["action"] == "REPLACE" and rows["cassette"]["action"] == "REPLACE"
    assert inv.open_installation(session, old_chain.id) is None
    assert old_chain.disposition == "SOLD"                  # chosen outcome
    assert old_pads.disposition == "DISCARDED"              # default for pads
    assert old_cassette.disposition == "STORED"             # default for a cassette
    assert km(session, old_chain) == 300                    # history kept
    new_cassette = inv.open_installation(session, rows["cassette"]["component_id"])
    assert new_cassette.parent_component_id == rear.id


def test_undo_takes_back_the_whole_import(session):
    b = bike(session)
    _, rear = wheels(session, b)
    old_chain = part(session, "CHAIN", "Chain A")
    inv.install(session, old_chain.id, bike_id=b.id, at="2026-08-01")
    res = run_import(session, b, occupied="REPLACE")
    ws_svc.undo(session, res["work_session_id"], "wrong bike")
    assert inv.open_installation(session, old_chain.id) is not None
    assert old_chain.disposition == "STORED"
    labels = {r["label"] for r in inv.bike_setup(session, b)}
    assert labels == {"Front wheel", "Rear wheel", "Chain A"}
    created = [session.get(Component, c["component_id"]) for c in res["created"]]
    assert all(c.disposition == "VOIDED" for c in created)  # kept as records, not deleted


def test_second_import_reuses_products_and_gets_unique_labels(session):
    b1, b2 = bike(session), bike(session, name="BMC Roadmachine")
    first = run_import(session, b1)
    products = session.scalar(select(func.count(Product.id)))
    second = run_import(session, b2)
    assert session.scalar(select(func.count(Product.id))) == products
    assert second["new_products"] == 0
    third = run_import(session)                             # no bike: all spares, labels still unique
    assert third["counts"]["SPARE"] == len(third["items"])
    labels = [c["label"] for r in (first, second, third) for c in r["created"]]
    assert len(labels) == len(set(labels))


def test_options_and_item_selection(session):
    b = bike(session)
    p = gs.plan(session, R8100, bike_id=b.id, options={"bottom_bracket": "NONE", "power_meter": "YES"},
                include=["crankset", "chainring_outer", "battery", "wires"])
    rows = by_key(p)
    assert set(rows) == {"crankset", "chainring_outer", "battery", "wires"}
    assert rows["crankset"]["model"] == "FC-R8100-P 172.5 mm"
    p2 = gs.plan(session, R8100, bike_id=b.id, include=["chainring_outer"])
    assert by_key(p2)["chainring_outer"]["action"] == "SPARE"   # crankset not part of this import
    assert "bottom_bracket" not in by_key(gs.plan(session, R8100, options={"bottom_bracket": "NONE"}))
    with pytest.raises(DomainError, match="not offered"):
        gs.plan(session, R8100, options={"cassette": "11-36"})
    with pytest.raises(DomainError, match="Unknown items"):
        gs.plan(session, R8100, include=["saddle"])
    # planning changes nothing
    assert session.scalar(select(func.count(Installation.id))) == 0


def test_groupset_import_over_http(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    c.headers.update({"X-BikeLog-Token": "t"})
    b = c.post("/api/bikes", json={"name": "TIME NXR"}).json()
    templates = c.get("/api/groupsets").json()
    assert templates[0]["code"] == R8100 and all(t["verified"] is False for t in templates)
    assert {t["speeds"] for t in templates} == {12, 13}
    body = {"bike_id": b["id"], "options": {"gearing": "52-36"}}
    plan = c.post(f"/api/groupsets/{R8100}/plan", json=body).json()
    assert plan["counts"]["INSTALL"] > 10
    dry = c.post(f"/api/groupsets/{R8100}/import?dry_run=true", json={**body, "at": "2026-10-25"})
    assert dry.status_code == 200
    assert c.get(f"/api/bikes/{b['id']}").json()["setup"] == []   # dry run changed nothing
    r = c.post(f"/api/groupsets/{R8100}/import", json={**body, "at": "2026-10-25"}).json()
    ws = r["result"]["work_session_id"]
    assert len(c.get(f"/api/bikes/{b['id']}").json()["setup"]) == r["result"]["counts"]["INSTALL"]
    assert c.post(f"/api/work-sessions/{ws}/undo", json={"reason": "test"}).status_code == 200
    assert c.get(f"/api/bikes/{b['id']}").json()["setup"] == []


@pytest.mark.parametrize("code", sorted(gs.TEMPLATES))
def test_every_template_installs_completely_on_a_bike_with_wheels(session, code):
    """Each shipped groupset (12 and 13 speed) goes on a bike in one action, every default part placed."""
    b = bike(session, f"Bike {code}")
    wheels(session, b)
    ws = ws_svc.begin(session, at="2026-10-25", bike_id=b.id, title="Groupset")
    res = gs.import_groupset(session, code, at="2026-10-25", bike_id=b.id, work_session_id=ws.id)
    assert res["counts"]["SPARE"] == 0 and res["counts"]["REPLACE"] == 0
    assert all(r["action"] == "INSTALL" for r in res["items"])
    assert inv.shifting_of(session, b) == ("ELECTRONIC" if any(r["type"] == "BATTERY" for r in res["items"])
                                           else None)


def test_sram_axs_batteries_sit_on_the_derailleurs_and_count_ride_hours(session):
    from bikelog.services import maintenance as m
    b = bike(session)
    wheels(session, b)
    ws = ws_svc.begin(session, at="2026-10-25", bike_id=b.id, title="Groupset")
    res = gs.import_groupset(session, "SRAM_RED_AXS_E1_2X12", at="2026-10-25", bike_id=b.id, work_session_id=ws.id)
    rows = by_key(res)
    for end in ("front", "rear"):
        inst = inv.open_installation(session, rows[f"battery_{end}"]["component_id"])
        assert inst.parent_component_id == rows[f"{end}_derailleur"]["component_id"]
        battery = inv.get_component(session, rows[f"battery_{end}"]["component_id"])
        rule = next(r for r in m.effective_rules(session, battery) if r.rule_code == "DI2_BATTERY_CHARGE")
        assert rule.interval_hours == 55 and rule.interval_km is None and rule.name == "Charge AXS battery"


def test_13_speed_and_mechanical_templates(session):
    red13 = gs.TEMPLATES["SRAM_RED_XPLR_AXS_1X13"]
    assert red13["speeds"] == 13 and not red13["verified"]
    keys = {i["key"] for i in gs.items(red13, *gs.choose(red13, None))}
    assert "front_derailleur" not in keys and "chainring" in keys and "battery_front" not in keys
    apex = gs.TEMPLATES["SRAM_APEX_XPLR_1X12"]
    mech = {i["key"] for i in gs.items(apex, *gs.choose(apex, {"shifting": "MECH"}))}
    axs = {i["key"] for i in gs.items(apex, *gs.choose(apex, {"shifting": "AXS"}))}
    assert "cable_rear" in mech and "battery_rear" not in mech
    assert "battery_rear" in axs and "cable_rear" not in axs
    r7100 = {i["key"] for i in gs.TEMPLATES["SHIMANO_105_R7100"]["items"]}
    assert {"cable_front", "cable_rear", "housing_front", "housing_rear"} <= r7100 and "battery" not in r7100
