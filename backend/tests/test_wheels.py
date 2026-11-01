"""A wheelset always has a front and a rear wheel (DECISIONS 108), so a tire has somewhere to go."""
from bikelog.services import inventory as inv
from bikelog.services import spares, wheels
from bikelog.services.usage import component_usage

from helpers import bike, part, ride


def test_wheelset_without_wheels_gets_them_with_its_history(session):
    b = bike(session)
    ws = part(session, "WHEELSET", "Zipp 303")
    inv.install(session, ws.id, bike_id=b.id, slot="WHEELSET", at="2026-09-01")
    ride(session, b, "2026-09-10", 80)
    assert spares.mount_targets(session, "TIRE", under=ws.id)["targets"] == []
    assert wheels.ensure_wheels(session) == 2
    t = spares.mount_targets(session, "TIRE", under=ws.id)["targets"]
    assert [x["parent_type"] for x in t] == ["FRONT_WHEEL", "REAR_WHEEL"]
    front = inv.get_component(session, t[0]["parent_component_id"])
    assert front.label == "Zipp 303 front wheel" and component_usage(session, front)["total_km"] == 80
    assert wheels.ensure_wheels(session) == 0          # once only


def test_wheel_taken_out_on_purpose_is_not_put_back(session):
    ws = part(session, "WHEELSET", "Old set")
    fw = part(session, "FRONT_WHEEL", "Old front")
    inv.install(session, fw.id, parent_component_id=ws.id, slot="FRONT_WHEEL", at="2026-09-01")
    inv.remove(session, fw.id, at="2026-09-05")
    assert wheels.ensure_wheels(session, ws.id) == 1   # only the rear, which it never had


def test_move_front_tire_to_rear_and_swap_keep_km(session):
    b = bike(session)
    ws = part(session, "WHEELSET", "Zipp 303")
    inv.install(session, ws.id, bike_id=b.id, slot="WHEELSET", at="2026-09-01")
    wheels.ensure_wheels(session, ws.id)
    t = spares.mount_targets(session, "TIRE", under=ws.id)["targets"]
    fw, rw = t[0]["parent_component_id"], t[1]["parent_component_id"]
    a, c = part(session, "TIRE", "Tire A"), part(session, "TIRE", "Tire B")
    inv.install(session, a.id, parent_component_id=fw, slot="TIRE", at="2026-09-01")
    ride(session, b, "2026-09-10", 100)
    inv.move(session, a.id, at="2026-09-11", parent_component_id=rw, slot="TIRE")
    inv.install(session, c.id, parent_component_id=fw, slot="TIRE", at="2026-09-11")
    ride(session, b, "2026-09-12", 50)
    inv.move(session, a.id, at="2026-09-13", parent_component_id=fw, slot="TIRE", swap=True)
    ride(session, b, "2026-09-14", 30)
    assert component_usage(session, a)["total_km"] == 180 and component_usage(session, c)["total_km"] == 80
    assert inv.location(session, a)["parent_component_id"] == fw and inv.location(session, c)["parent_component_id"] == rw
