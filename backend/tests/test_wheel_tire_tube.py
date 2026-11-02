"""Wheel page: the tire and inner tube on it now and before, each with its own km (Dirk 2026-11-02)."""
from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import repairs, stock, wheels

from helpers import bike, part, ride


def test_wheel_shows_current_tube_and_tube_history_with_own_km(session):
    b = bike(session, name="Synapse")
    rw = part(session, "REAR_WHEEL", "Zipp rear")
    inv.install(session, rw.id, at="2026-08-01", bike_id=b.id)
    ride(session, b, "2026-08-10", 2000)                      # the wheel has km before the tube
    old = part(session, "INNER_TUBE", "Conti old")
    inv.install(session, old.id, at="2026-09-01", parent_component_id=rw.id)
    r = ride(session, b, "2026-09-01", 100)                    # the install day counts
    ride(session, b, "2026-09-05", 200)
    tubes = stock.add_consumable(session, name="Conti Race 28", component_type="INNER_TUBE", tracking_mode="COUNTED")
    stock.consumable_txn(session, tubes.id, kind="PURCHASE", qty=2, on="2026-09-01")
    g = inc.log(session, r.id, incident_type="FLAT",
                affected=[o["key"] for o in inc.choices(session, r, "FLAT") if o["label"] == "Rear tube: Conti old"])
    e = repairs.fix_options(session, g)["parts"][0]
    repairs.fix(session, g, at="2026-09-06", parts=[
        {"entry_id": e["entry_id"], "action": "REPLACED", "source": {"kind": "stock", "id": tubes.id},
         "old_outcome": "DISCARDED"}])
    ride(session, b, "2026-09-10", 50)

    tt = wheels.tire_and_tube(session, rw)["INNER_TUBE"]
    cur = tt["current"]
    assert cur["label"] == "Conti Race 28" and cur["km_here"] == 50 and cur["km_total"] == 50 and cur["punctures"] == 0
    prev = tt["history"][1]
    assert prev["label"] == "Conti old" and prev["km_here"] == 300 and prev["punctures"] == 1 and not prev["current"]
    assert prev["removed_at"] and "discarded" in (prev["ended"] or "")
    assert wheels.tire_and_tube(session, rw)["TIRE"] == {"current": None, "history": []}
