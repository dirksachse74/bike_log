"""Fixing incidents (Dirk 2026-10-26): per damaged part replaced (spare, stock or new; the old part keeps its
km), patched/repaired, or nothing yet; solved when every part is handled; undo brings everything back."""
import pytest

from bikelog.models import JournalEntry
from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import repairs
from bikelog.services import stock
from bikelog.services.errors import DomainError

from helpers import bike, km, part, ride


def setup(session):
    b = bike(session)
    fw, rw = part(session, "FRONT_WHEEL", "Zipp front"), part(session, "REAR_WHEEL", "Zipp rear")
    inv.install(session, fw.id, at="2026-09-01", bike_id=b.id)
    inv.install(session, rw.id, at="2026-09-01", bike_id=b.id)
    ft = part(session, "TIRE", "GP5000 front")
    inv.install(session, ft.id, at="2026-09-01", parent_component_id=fw.id)
    tubes = stock.add_consumable(session, name="Conti Race 28", component_type="INNER_TUBE", tracking_mode="COUNTED")
    stock.consumable_txn(session, tubes.id, kind="PURCHASE", qty=3, on="2026-09-01")
    r = ride(session, b, "2026-10-05", 80)
    return b, fw, rw, ft, tubes, r


def keys(session, r):
    return {o["label"]: o["key"] for o in inc.choices(session, r, "FLAT")}


def entry(session, group, label):
    opts = repairs.fix_options(session, group)
    return next(p for p in opts["parts"] if p["label"] == label)


def test_tube_from_stock_on_the_road_solves_the_flat_and_undo_brings_it_back(session):
    b, fw, rw, ft, tubes, r = setup(session)
    group = inc.log(session, r.id, incident_type="FLAT", affected=[keys(session, r)["Rear tube"]])
    p = entry(session, group, "Rear tube")
    assert p["kind"] == "POSITION" and p["options"]["stock"][0]["qty"] == 3 and p["repair_label"] == "Patched"
    res = repairs.fix(session, group, at="2026-10-05", parts=[
        {"entry_id": p["entry_id"], "action": "REPLACED", "source": {"kind": "stock", "id": tubes.id}}])
    assert res["solved"] and "2 left" in res["texts"][0]
    assert stock.level(session, tubes)["qty"] == 2
    row = inc.ride_incidents(session, r.id)[0]
    assert row["resolved_on"] == "2026-10-05" and row["affected"][0]["repair"] == "REPLACED" and row["has_fix"]
    assert not row["fixable"]
    repairs.undo_fix(session, group)
    assert stock.level(session, tubes)["qty"] == 3
    row = inc.ride_incidents(session, r.id)[0]
    assert row["open"] and row["affected"][0]["repair"] is None and row["fixable"]


def test_tire_and_tube_fixed_in_two_steps(session):
    """Tube patched at the roadside, tire replaced at home later: open until both are handled."""
    b, fw, rw, ft, tubes, r = setup(session)
    k = keys(session, r)
    group = inc.log(session, r.id, incident_type="FLAT", affected=[k["Front tube"], k["Front tire: GP5000 front"]])
    tube, tire = entry(session, group, "Front tube"), entry(session, group, "GP5000 front")
    assert tire["kind"] == "PART" and tire["installed"] and tire["options"]["replace"]
    res = repairs.fix(session, group, at="2026-10-05", parts=[
        {"entry_id": tube["entry_id"], "action": "REPAIRED"}, {"entry_id": tire["entry_id"], "action": "NONE"}])
    assert not res["solved"] and inc.ride_incidents(session, r.id)[0]["open"]
    assert inc.all_incidents(session, open_only=True)[0]["group"] == group       # still in Upcoming tasks
    spare = part(session, "TIRE", "GP5000 spare")
    ride(session, b, "2026-10-08", 40)
    res = repairs.fix(session, group, at="2026-10-10", parts=[
        {"entry_id": tire["entry_id"], "action": "REPLACED", "source": {"kind": "spare", "id": spare.id},
         "old_outcome": "DISCARDED"}])
    assert res["solved"] and inc.ride_incidents(session, r.id)[0]["resolved_on"] == "2026-10-10"
    assert inv.location(session, spare)["parent_component_id"] == fw.id
    assert km(session, ft) == 120 and inv.get_component(session, ft.id).disposition == "DISCARDED"
    with pytest.raises(DomainError, match="already replaced"):
        repairs.fix(session, group, at="2026-10-11", parts=[{"entry_id": tire["entry_id"], "action": "REPAIRED"}])
    with pytest.raises(DomainError, match="before the ride"):
        g2 = inc.log(session, r.id, incident_type="FLAT", affected=[k["Rear tube"]])
        repairs.fix(session, g2, at="2026-10-01", parts=[
            {"entry_id": entry(session, g2, "Rear tube")["entry_id"], "action": "REPAIRED"}])


def test_recorded_tube_patches_are_counted(session):
    b, fw, rw, ft, tubes, r = setup(session)
    tube = part(session, "INNER_TUBE", "Latex rear")
    inv.install(session, tube.id, at="2026-09-01", parent_component_id=rw.id)
    for when in ("2026-10-05", "2026-10-06"):
        rr = ride(session, b, when, 30)
        g = inc.log(session, rr.id, incident_type="FLAT", affected=[keys(session, rr)["Rear tube: Latex rear"]])
        res = repairs.fix(session, g, at=when, parts=[
            {"entry_id": entry(session, g, "Latex rear")["entry_id"], "action": "REPAIRED"}])
    assert "patch 2 on this tube" in res["texts"][0]


def test_a_new_tire_needs_the_wheel_and_other_incidents_are_not_fixable(session):
    b = bike(session)
    r = ride(session, b, "2026-10-05", 30)
    group = inc.log(session, r.id, incident_type="FLAT", affected=[keys(session, r)["Rear tire"]])
    spare = part(session, "TIRE", "Spare tire")
    p = entry(session, group, "Rear tire")
    assert p["options"]["spares"] == [] and p["options"]["wheel_label"] is None
    with pytest.raises(DomainError, match="No rear wheel recorded"):
        repairs.fix(session, group, at="2026-10-05", parts=[
            {"entry_id": p["entry_id"], "action": "REPLACED", "source": {"kind": "spare", "id": spare.id}}])
    res = repairs.fix(session, group, at="2026-10-05", parts=[
        {"entry_id": p["entry_id"], "action": "REPLACED", "source": {"kind": "new"}}])
    assert res["solved"] and "not tracked" in res["texts"][0]
    fit = inc.log(session, r.id, incident_type="FIT", affected=["NUMB_HANDS"])
    assert not next(x for x in inc.ride_incidents(session, r.id) if x["group"] == fit)["fixable"]


def test_swap_tube_at_a_wheel_takes_one_from_stock(session):
    b, fw, rw, ft, tubes, r = setup(session)
    opts = repairs.position_options(session, b.id, "FRONT_WHEEL", "TUBE")
    assert opts["wheel_label"] == "Zipp front" and opts["installed_component_id"] is None
    from bikelog.services import worksessions
    ws = worksessions.begin(session, at="2026-10-06", bike_id=b.id, title="Swap tube")
    text = repairs.replace_at_position(session, bike_id=b.id, wheel="FRONT_WHEEL", damage="TUBE", at="2026-10-06",
                                       source={"kind": "stock", "id": tubes.id}, work_session_id=ws.id,
                                       reason="swap tube")
    assert "2 left" in text and stock.level(session, tubes)["qty"] == 2
    worksessions.undo(session, ws.id)
    assert stock.level(session, tubes)["qty"] == 3
    assert session.query(JournalEntry).count() == 0
