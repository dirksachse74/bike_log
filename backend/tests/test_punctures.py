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
    inc.log(session, r2.id, incident_type="FLAT",
            affected=[k["Rear tube"], k["Front tube: Schwalbe Aerothan"], k["Front tire: GP5000 front"]])

    rep = punctures.report(session)
    assert rep["total"] == 3
    rows = {(r["on"], r["wheel"]): r for r in rep["rows"]}
    first = rows[("2026-09-10", "Rear")]
    assert first["tube_model"] == "Not recorded in Bike Log" and first["tire_model"] == "GP5000 rear"
    assert first["conditions"] == "WET" and first["damage"] == "Tube"
    # the second rear flat was the Conti tube put in at the first fix
    second = rows[("2026-10-01", "Rear")]
    assert second["tube_model"] == "Conti Race 28" and second["tube_inferred"]
    front = rows[("2026-10-01", "Front")]
    assert front["tube_model"] == "Schwalbe Aerothan" and front["damage"] == "Tube and tire"
    by_tube = {x["model"]: x for x in rep["by_tube"]}
    assert by_tube["Conti Race 28"]["punctures"] == 1 and by_tube["Conti Race 28"]["km"] == 250   # 200 + 50
    assert by_tube["Schwalbe Aerothan"]["punctures"] == 1 and by_tube["Schwalbe Aerothan"]["km"] == 350
    assert by_tube["Schwalbe Aerothan"]["km_per_puncture"] == 350
    by_tire = {x["model"]: x for x in rep["by_tire"]}
    assert by_tire["GP5000 rear"]["punctures"] == 2 and by_tire["GP5000 front"]["punctures"] == 1
    assert {x["name"]: x["punctures"] for x in rep["by_wheel"]} == {"Rear": 2, "Front": 1}
    assert {x["name"]: x["punctures"] for x in rep["by_conditions"]} == {"Dry": 2, "Wet": 1}
    # a removed incident does not count
    inc.remove(session, g1)
    assert punctures.report(session)["total"] == 2
