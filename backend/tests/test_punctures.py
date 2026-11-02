"""Puncture statistics (Dirk 2026-11-01, DECISIONS 117): per tube and tire model, km per puncture."""
from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import punctures, repairs, stock

from helpers import bike, part, ride


def _keys(session, r):
    return {o["label"]: o["key"] for o in inc.choices(session, r, "FLAT")}


def test_punctures_by_tube_and_tire_model(session):
    b = bike(session, name="Synapse")
    fw, rw = part(session, "FRONT_WHEEL", "Zipp front"), part(session, "REAR_WHEEL", "Zipp rear")
    for w in (fw, rw):
        inv.install(session, w.id, at="2026-09-01", bike_id=b.id)
    ft = part(session, "TIRE", "GP5000 front")
    rt = part(session, "TIRE", "GP5000 rear")
    inv.install(session, ft.id, at="2026-09-01", parent_component_id=fw.id)
    inv.install(session, rt.id, at="2026-09-01", parent_component_id=rw.id)
    # the front tube is a recorded part; the rear tubes come from stock
    tpu = part(session, "INNER_TUBE", "Schwalbe Aerothan")
    inv.install(session, tpu.id, at="2026-09-01", parent_component_id=fw.id)
    tubes = stock.add_consumable(session, name="Conti Race 28", component_type="INNER_TUBE",
                                 tracking_mode="COUNTED")
    stock.consumable_txn(session, tubes.id, kind="PURCHASE", qty=3, on="2026-09-01")

    r1 = ride(session, b, "2026-09-10", 100, conditions="WET")
    k = _keys(session, r1)
    g1 = inc.log(session, r1.id, incident_type="FLAT", affected=[k["Rear tube"]])
    e = next(p for p in repairs.fix_options(session, g1)["parts"] if p["label"] == "Rear tube")
    repairs.fix(session, g1, at="2026-09-10", parts=[
        {"entry_id": e["entry_id"], "action": "REPLACED", "source": {"kind": "stock", "id": tubes.id}}])
    ride(session, b, "2026-09-20", 200)
    r2 = ride(session, b, "2026-10-01", 50, conditions="DRY")
    k = _keys(session, r2)
    # the tube from stock went onto the recorded rear wheel as its own part (Dirk 2026-11-02)
    inc.log(session, r2.id, incident_type="FLAT",
            affected=[k["Rear tube: Conti Race 28"], k["Front tube: Schwalbe Aerothan"], k["Front tire: GP5000 front"]])

    rep = punctures.report(session)
    assert rep["total"] == 3
    rows = {(r["on"], r["wheel"]): r for r in rep["rows"]}
    first = rows[("2026-09-10", "Rear")]
    assert first["tube_model"] == "Not recorded in Bike Log" and first["tire_model"] == "GP5000 rear"
    assert first["conditions"] == "WET" and first["damage"] == "Tube"
    # the second rear flat was the Conti tube put in at the first fix
    second = rows[("2026-10-01", "Rear")]
    assert second["tube_model"] == "Conti Race 28" and not second["tube_inferred"] and second["tube_id"]
    front = rows[("2026-10-01", "Front")]
    assert front["tube_model"] == "Schwalbe Aerothan" and front["damage"] == "Tube and tire"
    # per model each tube / tire on its own line, with its own km (Dirk: adding km of different tires makes no sense)
    by_tube = {x["model"]: x for x in rep["by_tube"]}
    conti = by_tube["Conti Race 28"]     # its own km: in after the flat ride, 200 + 50
    assert conti["punctures"] == 1 and len(conti["items"]) == 1
    assert conti["items"][0]["km"] == 250 and conti["items"][0]["km_per_puncture"] == 250 and conti["items"][0]["in_use"]
    aero = by_tube["Schwalbe Aerothan"]["items"][0]
    assert aero["punctures"] == 1 and aero["km"] == 350 and aero["km_per_puncture"] == 350
    assert "km" not in by_tube["Schwalbe Aerothan"]                                 # no summed km per model
    by_tire = {x["model"]: x for x in rep["by_tire"]}
    assert by_tire["GP5000 rear"]["punctures"] == 2 and by_tire["GP5000 front"]["punctures"] == 1
    assert by_tire["GP5000 front"]["items"][0]["km"] == 350
    assert {x["name"]: x["punctures"] for x in rep["by_wheel"]} == {"Rear": 2, "Front": 1}
    assert {x["name"]: x["punctures"] for x in rep["by_conditions"]} == {"Dry": 2, "Wet": 1}
    # a removed incident does not count
    inc.remove(session, g1)
    assert punctures.report(session)["total"] == 2


def test_stock_tube_without_a_recorded_wheel_is_inferred_from_the_last_fix(session):
    """No wheel recorded on the bike: a tube from stock stays a stock use; the next flat on that wheel was it."""
    b = bike(session, name="Old bike")
    tubes = stock.add_consumable(session, name="Conti Race 28", component_type="INNER_TUBE",
                                 tracking_mode="COUNTED")
    stock.consumable_txn(session, tubes.id, kind="PURCHASE", qty=3, on="2026-09-01")
    r1 = ride(session, b, "2026-09-10", 100)
    g1 = inc.log(session, r1.id, incident_type="FLAT", affected=[_keys(session, r1)["Rear tube"]])
    e = next(p for p in repairs.fix_options(session, g1)["parts"] if p["label"] == "Rear tube")
    repairs.fix(session, g1, at="2026-09-10", parts=[
        {"entry_id": e["entry_id"], "action": "REPLACED", "source": {"kind": "stock", "id": tubes.id}}])
    assert stock.level(session, tubes)["qty"] == 2
    ride(session, b, "2026-09-20", 200)
    r2 = ride(session, b, "2026-10-01", 50)
    inc.log(session, r2.id, incident_type="FLAT", affected=[_keys(session, r2)["Rear tube"]])
    rows = {r["on"]: r for r in punctures.report(session)["rows"]}
    assert rows["2026-09-10"]["tube_model"] == "Not recorded in Bike Log"
    assert rows["2026-10-01"]["tube_model"] == "Conti Race 28" and rows["2026-10-01"]["tube_inferred"]
    by_tube = {x["model"]: x for x in punctures.report(session)["by_tube"]}
    stock_line = by_tube["Conti Race 28"]["items"][0]
    assert stock_line["component_id"] is None and stock_line["km"] == 250 and stock_line["punctures"] == 1  # 200 + 50


def test_two_tires_of_one_model_each_keep_their_own_km(session):
    """Two GP5000 tires: each line shows its own km and km per puncture, nothing is added up."""
    b = bike(session, name="Synapse")
    fw, rw = part(session, "FRONT_WHEEL", "Zipp front"), part(session, "REAR_WHEEL", "Zipp rear")
    for w in (fw, rw):
        inv.install(session, w.id, at="2026-09-01", bike_id=b.id)
    ft = part(session, "TIRE", "GP5000")
    rt = part(session, "TIRE", "GP5000 (2)")
    inv.install(session, ft.id, at="2026-09-01", parent_component_id=fw.id)
    inv.install(session, rt.id, at="2026-09-15", parent_component_id=rw.id)
    ride(session, b, "2026-09-10", 100)
    r = ride(session, b, "2026-09-20", 60)
    inc.log(session, r.id, incident_type="FLAT", affected=[_keys(session, r)["Rear tire: GP5000 (2)"]])
    gp = {x["model"]: x for x in punctures.report(session)["by_tire"]}["GP5000"]
    items = {x["label"]: x for x in gp["items"]}
    assert gp["punctures"] == 1 and set(items) == {"GP5000", "GP5000 (2)"}
    assert items["GP5000 (2)"]["km"] == 60 and items["GP5000 (2)"]["km_per_puncture"] == 60
    assert items["GP5000"]["km"] == 160 and items["GP5000"]["punctures"] == 0 and items["GP5000"]["km_per_puncture"] is None
