"""Parts inside parts (wheelset → wheels → tire/hub/bearings/sensor; chain → quick link; rear derailleur →
pulley wheels), each with its own km; ride-hours and "number of chains" reminders; charging."""
import pytest

from bikelog.models import UsageProfile
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import rides as rides_svc
from bikelog.services import spares
from bikelog.services.errors import DomainError

from helpers import bike, km, part, ride


def status(session, comp, code):
    return next(r for r in m.component_status(session, comp) if r["rule_code"] == code)


def wheels(session, b):
    front = part(session, "FRONT_WHEEL", "Reynolds front")
    rear = part(session, "REAR_WHEEL", "Reynolds rear")
    inv.install(session, front.id, at="2026-09-01", bike_id=b.id, slot="FRONT_WHEEL")
    inv.install(session, rear.id, at="2026-09-01", bike_id=b.id, slot="REAR_WHEEL")
    return front, rear


def test_wheelset_children_keep_their_own_km_and_move_together(session):
    b = bike(session)
    front, rear = wheels(session, b)
    inv.set_starting_usage(session, component_id=front.id, km=2000, effective="2026-09-01", is_estimate=True)
    tire_f = part(session, "TIRE", "GP5000 front")                         # new: 0 km
    tire_r = part(session, "TIRE", "GP5000 rear")
    inv.set_starting_usage(session, component_id=tire_r.id, km=1000, effective="2026-09-01", is_estimate=False)
    hub = part(session, "HUB", "DT 240 front hub")
    bearings = part(session, "HUB_BEARINGS", "Front hub bearings")
    sensor = part(session, "SENSOR", "Magene S3+ speed")
    for c, parent, slot in ((tire_f, front, "TIRE"), (tire_r, rear, "TIRE"), (hub, front, "HUB"),
                            (bearings, hub, "BEARINGS"), (sensor, front, "SENSOR_SPEED")):
        inv.install(session, c.id, at="2026-09-01", parent_component_id=parent.id, slot=slot)
    ride(session, b, "2026-09-10", 50)
    res = inv.group_wheels(session, b.id, at="2026-10-01", label="Reynolds AR58")
    ws = inv.get_component(session, res["wheelset_id"])
    ride(session, b, "2026-10-05", 40)
    assert km(session, front) == 2090 and km(session, tire_f) == 90 and km(session, tire_r) == 1090
    assert km(session, bearings) == 90 and km(session, sensor) == 90
    assert km(session, ws) == 40                                            # counts from grouping on
    # wheels cannot be mounted directly again while the wheelset is there
    spare = part(session, "FRONT_WHEEL", "Spare front")
    with pytest.raises(DomainError, match="wheelset"):
        inv.install(session, spare.id, at="2026-10-06", bike_id=b.id, slot="FRONT_WHEEL")
    # moving the wheelset to another bike takes everything on it along
    b2 = bike(session, "BMC Roadmachine")
    inv.move(session, ws.id, at="2026-10-10", bike_id=b2.id, slot="WHEELSET")
    ride(session, b2, "2026-10-12", 30)
    ride(session, b, "2026-10-12", 25)
    assert km(session, tire_f) == 120 and km(session, front) == 2120 and km(session, sensor) == 120
    # a trainer ride with wheels off: wheelset, wheels and everything on them count nothing
    trainer = session.query(UsageProfile).filter_by(code="DIRECT_DRIVE_TRAINER").one()
    rides_svc.add_manual_ride(session, bike_id=b2.id, when="2026-10-13", distance=30, sport_type="VirtualRide",
                              usage_profile_code=trainer.code)
    assert km(session, bearings) == 120 and km(session, ws) == 70


def test_quick_link_moves_to_the_next_chain_until_its_limit(session):
    b = bike(session)
    chain_a = part(session, "CHAIN", "Chain A")
    link = part(session, "QUICK_LINK", "Connex 12s")
    inv.install(session, chain_a.id, at="2026-09-01", bike_id=b.id)
    inv.install(session, link.id, at="2026-09-01", parent_component_id=chain_a.id)
    assert status(session, link, "QUICK_LINK_CHAINS")["status"] == "OK"
    opts = spares.replace_options(session, chain_a.id)
    assert opts["children"][0]["component_id"] == link.id and opts["children"][0]["carry_over"] is True
    res = inv.replace(session, chain_a.id, at="2026-10-01", new={"label": "Chain B"}, carry_over=[link.id],
                      old_outcome="DISCARDED")
    chain_b = inv.get_component(session, res["new_component_id"])
    assert inv.location(session, link)["parent_component_id"] == chain_b.id
    st = status(session, link, "QUICK_LINK_CHAINS")
    assert st["status"] == "DUE_SOON" and "Chain A, Chain B" in st["explanation"]
    # at the next chain change the dialog suggests leaving it behind (replace it)
    opts = spares.replace_options(session, chain_b.id)
    assert opts["children"][0]["carry_over"] is False and "replace it" in opts["children"][0]["note"]
    with pytest.raises(DomainError, match="mounted on the old part"):
        inv.replace(session, chain_b.id, at="2026-11-01", new={"label": "Chain C"}, carry_over=[chain_a.id])


def test_charging_by_ride_hours_needs_a_logged_charge(session):
    b = bike(session)
    pedals = part(session, "POWER_METER_PEDALS", "Assioma PRO RS-1")
    inv.install(session, pedals.id, at="2026-09-01", bike_id=b.id)
    st = status(session, pedals, "POWER_PEDALS_CHARGE")
    assert st["status"] == "INSUFFICIENT_INFO" and "no charge recorded" in st["explanation"]
    m.log_event(session, action_code="POWER_CHARGE", at="2026-09-02", component_id=pedals.id)
    for d in range(3, 9):
        ride(session, b, f"2026-09-0{d}" if d < 10 else f"2026-09-{d}", 200, duration_s=8 * 3600)   # 48 h
    st = status(session, pedals, "POWER_PEDALS_CHARGE")
    assert st["status"] == "DUE_SOON" and st["used_hours"] == 48 and "2.0 h left" in st["explanation"]
    ride(session, b, "2026-09-09", 30)                                           # no ride time recorded
    assert "1 ride without a ride time" in status(session, pedals, "POWER_PEDALS_CHARGE")["explanation"]
    m.log_event(session, action_code="POWER_CHARGE", at="2026-09-10", component_id=pedals.id)
    assert status(session, pedals, "POWER_PEDALS_CHARGE")["status"] == "OK"
    # the Di2 battery charges by distance, the sensor by hours or months
    batt = part(session, "BATTERY", "BT-DN300")
    inv.install(session, batt.id, at="2026-09-01", bike_id=b.id)
    assert status(session, batt, "DI2_BATTERY_CHARGE")["status"] == "INSUFFICIENT_INFO"
    shifters = part(session, "SHIFTERS", "ST-R8170")
    inv.install(session, shifters.id, at="2026-09-01", bike_id=b.id)
    assert status(session, shifters, "SHIFTER_COIN_CELLS")["status"] == "DISABLED"   # on only for wireless levers


def test_pulley_wheels_on_the_rear_derailleur(session):
    b = bike(session)
    rd = part(session, "REAR_DERAILLEUR", "RD-R8150")
    inv.install(session, rd.id, at="2026-09-01", bike_id=b.id)
    up = part(session, "PULLEY_WHEEL", "Upper pulley")
    lo = part(session, "PULLEY_WHEEL", "Lower pulley")
    inv.install(session, up.id, at="2026-09-01", parent_component_id=rd.id, slot="PULLEY_UPPER")
    inv.install(session, lo.id, at="2026-09-01", parent_component_id=rd.id, slot="PULLEY_LOWER")
    ride(session, b, "2026-09-05", 80)
    new_lo = part(session, "PULLEY_WHEEL", "Lower pulley 2")
    inv.replace(session, lo.id, at="2026-09-06", new_component_id=new_lo.id)
    ride(session, b, "2026-09-07", 20)
    assert km(session, up) == 100 and km(session, lo) == 80 and km(session, new_lo) == 20 and km(session, rd) == 100
    assert status(session, up, "PULLEY_CHECK")["status"] == "OK"


def test_mounted_parts_show_when_they_arrived_on_the_bike(session):
    """UAT B6: a tire on a wheel moved to another bike is on that bike since the move, not since it was fitted."""
    from helpers import bike, part
    a, b = bike(session, "Aurora SL"), bike(session, "Winter Allroad")
    wheel = part(session, "REAR_WHEEL", "Rear wheel")
    tire = part(session, "TIRE", "GP5000 rear")
    inv.install(session, wheel.id, bike_id=a.id, at="2026-09-01")
    inv.install(session, tire.id, parent_component_id=wheel.id, at="2026-09-01")
    inv.move(session, wheel.id, bike_id=b.id, at="2026-10-10")
    rows = {r["label"]: r for r in inv.bike_setup(session, b)}
    assert rows["GP5000 rear"]["since"] == "2026-10-10" and rows["GP5000 rear"]["mounted_since"] == "2026-09-01"
