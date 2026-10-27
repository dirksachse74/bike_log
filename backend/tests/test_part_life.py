"""Part life report and replacement forecast (DECISIONS 99)."""
from datetime import date

from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import part_life

from helpers import bike, part, ride


def chains(report):
    return next(t for t in report["types"] if t["code"] == "CHAIN")


def test_finished_chains_with_lifetime_reason_and_product_average(session):
    b = bike(session, purchase_date="2026-01-01")
    prod = inv.create_product(session, component_type="CHAIN", maker="Shimano", model="CN-M8100")
    a = part(session, "CHAIN", "Chain A", product_id=prod.id)
    inv.install(session, a.id, at="2026-01-01", bike_id=b.id, slot="CHAIN")
    ride(session, b, "2026-01-10", 2000, duration_s=4 * 3600)
    c2 = part(session, "CHAIN", "Chain B", product_id=prod.id)
    inv.replace(session, a.id, at="2026-04-01", new_component_id=c2.id, old_outcome="DISCARDED", reason="worn 0.5")
    ride(session, b, "2026-04-10", 3000)
    old = part(session, "CHAIN", "Old chain", prior_usage="RECORDED")   # km from before: estimated
    inv.set_starting_usage(session, component_id=old.id, km=1000, effective="2026-04-20", is_estimate=True)
    inv.replace(session, c2.id, at="2026-05-01", new_component_id=old.id, old_outcome="DISCARDED")
    ride(session, b, "2026-05-05", 100)
    t = chains(part_life.report(session))
    done = {r["label"]: r for r in t["finished"]}
    assert set(done) == {"Chain A", "Chain B"}
    assert done["Chain A"]["km"] == 2000 and done["Chain A"]["hours"] == 4.0
    assert done["Chain A"]["bikes"] == ["TIME NXR"] and done["Chain A"]["ended"] == "2026-04-01"
    assert done["Chain A"]["why"].startswith("Discarded") and "worn 0.5" in done["Chain A"]["why"]
    assert done["Chain A"]["months"] == 3.0 and done["Chain A"]["estimated"] is False
    avg = t["products"][0]
    assert avg["product"] == "Shimano CN-M8100" and avg["count"] == 2 and avg["avg_km"] == 2500
    use = {r["label"]: r for r in t["in_use"]}
    assert use["Old chain"]["km"] == 1100 and use["Old chain"]["estimated"] is True
    assert part_life.report(session, "TIRE")["types"] == []


def test_forecast_at_recent_pace_and_not_enough_rides(session):
    b = bike(session, purchase_date="2026-09-01")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, at="2026-09-01", bike_id=b.id, slot="CHAIN")
    today = date(2026, 10, 27)

    def hot_wax():
        return next(r for r in m.component_status(session, chain, today) if r["action_code"] == "WAX_HOT")
    ride(session, b, "2026-10-20", 50)
    f = hot_wax()["forecast"]
    assert f["status"] == "INSUFFICIENT_INFO" and "1 ride" in f["text"]
    ride(session, b, "2026-10-22", 50)
    ride(session, b, "2026-10-25", 40)                # 140 km in 4 weeks = 35 km/week; 360 km left
    f = hot_wax()["forecast"]
    assert f["status"] == "OK" and f["in_days"] == 72 and f["date"] == "2027-01-07"
    assert "not a safety check" in f["text"] and "35 km/week" in f["text"]
