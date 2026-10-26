"""Ride incidents linked to the ride and the affected parts; dry/wet per ride. Per-type choices from the parts
on the bike that day, several affected things per incident, edit, remove (void) and restore."""
import pytest

from bikelog.services import incidents as inc
from bikelog.services import inventory as inv
from bikelog.services import journal
from bikelog.services import rides as rides_svc
from bikelog.services.errors import DomainError, NotFound

from helpers import bike, part, ride


def setup(session):
    b = bike(session)
    wheel = part(session, "FRONT_WHEEL", "DT Swiss front")
    tire = part(session, "TIRE", "GP5000 front")
    inv.install(session, wheel.id, at="2026-10-01", bike_id=b.id, slot="FRONT_WHEEL")
    inv.install(session, tire.id, at="2026-10-01", parent_component_id=wheel.id, slot="TIRE")
    r = ride(session, b, "2026-10-20", 62, name="Rhine loop")
    return b, wheel, tire, r


def test_flat_on_a_ride_shows_on_ride_part_bike_and_incident_list(session):
    b, wheel, tire, r = setup(session)
    e = journal.add(session, text=None, ride_id=r.id, incident_type="FLAT", component_id=tire.id)
    assert e.kind == "ISSUE" and e.entry_on == "2026-10-20" and e.bike_id == b.id and e.text == "Flat tire"
    row = journal.row(session, e)
    assert row["ride_label"] == "Rhine loop (2026-10-20, 62 km)" and row["incident_label"] == "Flat tire"
    assert [x["id"] for x in journal.entries(session, ride_id=r.id)] == [e.id]
    assert [x["id"] for x in journal.entries(session, component_id=tire.id)] == [e.id]
    assert e.id in [x["id"] for x in journal.entries(session, bike_id=b.id)]
    assert [x["id"] for x in journal.incidents(session, bike_id=b.id)] == [e.id]
    assert journal.incidents(session, incident_type="CRASH") == []
    assert rides_svc.ride_row(session, r)["incidents"] == 1
    # fixed on the road: resolved, no longer in "open only"
    journal.update(session, e.id, resolved_on="2026-10-20")
    assert journal.incidents(session, open_only=True) == []
    # a crash with no part goes on the ride's bike
    c = journal.add(session, text="Slipped on wet leaves", ride_id=r.id, incident_type="CRASH")
    assert c.bike_id == b.id and c.component_id is None
    with pytest.raises(DomainError, match="incident_type"):
        journal.add(session, text="x", ride_id=r.id, incident_type="ALIENS")


def test_ride_conditions_are_local_and_validated(session):
    _, _, _, r = setup(session)
    rides_svc.edit_ride(session, r.id, {"conditions": "WET"})
    assert rides_svc.ride_row(session, r)["conditions"] == "WET"
    rides_svc.edit_ride(session, r.id, {"conditions": None})
    assert r.conditions is None
    with pytest.raises(DomainError, match="conditions"):
        rides_svc.edit_ride(session, r.id, {"conditions": "SNOW"})
    assert "conditions" not in rides_svc.SOURCE_FIELDS          # imports never overwrite it


def test_flat_on_the_tire_shows_on_the_wheel_and_the_wheelset(session):
    b, wheel, tire, r = setup(session)
    e = journal.add(session, text=None, ride_id=r.id, incident_type="FLAT", component_id=tire.id)
    rows = journal.entries(session, component_id=wheel.id)
    assert [x["id"] for x in rows if x.get("via_child")] == [e.id]
    # after the tire moved to another wheel, the old flat stays with the wheel it happened on
    other = part(session, "REAR_WHEEL", "DT Swiss rear")
    inv.install(session, other.id, at="2026-10-01", bike_id=b.id, slot="REAR_WHEEL")
    inv.move(session, tire.id, at="2026-10-22", parent_component_id=other.id, slot="TIRE")
    assert [x["id"] for x in journal.entries(session, component_id=other.id) if x.get("via_child")] == []
    assert [x["id"] for x in journal.entries(session, component_id=wheel.id) if x.get("via_child")] == [e.id]


def setup_bike(session):
    b = bike(session)
    fw = part(session, "FRONT_WHEEL", "Zipp front")
    rw = part(session, "REAR_WHEEL", "Zipp rear")
    inv.install(session, fw.id, at="2026-09-01", bike_id=b.id)
    inv.install(session, rw.id, at="2026-09-01", bike_id=b.id)
    ft = part(session, "TIRE", "GP5000 front")
    rt = part(session, "TIRE", "GP5000 rear")
    inv.install(session, ft.id, at="2026-09-01", parent_component_id=fw.id)
    inv.install(session, rt.id, at="2026-09-01", parent_component_id=rw.id)
    rd = part(session, "REAR_DERAILLEUR", "RD-R8150")
    fd = part(session, "FRONT_DERAILLEUR", "FD-R8150")
    inv.install(session, rd.id, at="2026-09-01", bike_id=b.id)
    inv.install(session, fd.id, at="2026-09-01", bike_id=b.id)
    return b, {"fw": fw, "rw": rw, "ft": ft, "rt": rt, "rd": rd, "fd": fd}


def labels(rows):
    return [r["label"] for r in rows]


def test_flat_offers_front_and_rear_tire_only(session):
    b, p = setup_bike(session)
    r = ride(session, b, "2026-09-10", 60)
    opts = inc.choices(session, r, "FLAT")
    assert labels(opts) == ["Front tire: GP5000 front", "Rear tire: GP5000 rear"]
    assert [o["component_id"] for o in opts] == [p["ft"].id, p["rt"].id]
    shifting = labels(inc.choices(session, r, "SHIFTING"))
    assert shifting[:2] == ["Front derailleur: FD-R8150", "Rear derailleur: RD-R8150"]
    assert "Shifters" in shifting                    # not recorded: offered by name
    fit = labels(inc.choices(session, r, "FIT"))
    assert {"Numb hands", "Numb toes", "Back pain", "Leg pain", "Neck pain"} <= set(fit)
    assert all(o["component_id"] is None for o in inc.choices(session, r, "FIT"))
    battery = labels(inc.choices(session, r, "BATTERY"))
    assert {"Di2 / AXS system", "Power meter", "Head unit / computer", "Speed sensor", "Cadence sensor"} <= set(battery)
    assert labels(inc.choices(session, r, "LOOSE"))[0] == "Stem (loose handlebar)"


def test_flat_without_tires_recorded_offers_the_positions(session):
    b = bike(session)
    r = ride(session, b, "2026-09-10", 60)
    opts = inc.choices(session, r, "FLAT")
    assert labels(opts) == ["Front tire", "Rear tire"] and not any(o["recorded"] for o in opts)
    group = inc.log(session, r.id, incident_type="FLAT", affected=["FRONT_TIRE", "REAR_TIRE"], text="glass")
    row = inc.ride_incidents(session, r.id)[0]
    assert row["group"] == group and [a["label"] for a in row["affected"]] == ["Front tire", "Rear tire"]


def test_parts_are_those_on_the_bike_that_day(session):
    b, p = setup_bike(session)
    inv.remove(session, p["rt"].id, at="2026-09-20")
    new_rt = part(session, "TIRE", "GP5000 rear #2")
    inv.install(session, new_rt.id, at="2026-09-20", parent_component_id=p["rw"].id)
    before = ride(session, b, "2026-09-15", 50)
    after = ride(session, b, "2026-09-25", 50)
    assert "Rear tire: GP5000 rear" in labels(inc.choices(session, before, "FLAT"))
    assert "Rear tire: GP5000 rear #2" in labels(inc.choices(session, after, "FLAT"))


def test_two_flats_are_one_incident_on_both_tires(session):
    b, p = setup_bike(session)
    r = ride(session, b, "2026-09-10", 60)
    keys = [f"c{p['ft'].id}", f"c{p['rt'].id}"]
    group = inc.log(session, r.id, incident_type="FLAT", affected=keys, text="Two pinch flats")
    rows = inc.ride_incidents(session, r.id)
    assert len(rows) == 1 and [a["component_id"] for a in rows[0]["affected"]] == [p["ft"].id, p["rt"].id]
    assert rides_svc.ride_row(session, r)["incidents"] == 1          # one incident, two parts
    # each tire shows it in its own journal
    assert any(e["incident_group"] == group for e in journal.entries(session, component_id=p["rt"].id))
    with pytest.raises(DomainError, match="cannot have"):
        inc.log(session, r.id, incident_type="FLAT", affected=[f"c{p['rd'].id}"])


def test_edit_remove_and_restore(session):
    b, p = setup_bike(session)
    r = ride(session, b, "2026-09-10", 60)
    group = inc.log(session, r.id, incident_type="SHIFTING", affected=[f"c{p['rd'].id}"])
    inc.update(session, group, affected=[f"c{p['rd'].id}", f"c{p['fd'].id}"], text="Both misshifting",
               resolved_on="2026-09-11", fields={"affected", "text", "resolved_on"})
    row = inc.ride_incidents(session, r.id)[0]
    assert {a["component_id"] for a in row["affected"]} == {p["rd"].id, p["fd"].id}
    assert row["text"] == "Both misshifting" and row["resolved_on"] == "2026-09-11" and not row["open"]
    # untick the front derailleur: its entry is voided, not deleted
    inc.update(session, group, affected=[f"c{p['rd'].id}"], fields={"affected"})
    row = inc.ride_incidents(session, r.id)[0]
    assert [a["component_id"] for a in row["affected"]] == [p["rd"].id] and row["text"] == "Both misshifting"
    assert any(e["voided"] for e in journal.entries(session, component_id=p["fd"].id, include_voided=True))
    # change the type: the derailleur is not a flat, so it must be re-picked
    with pytest.raises(DomainError, match="cannot have"):
        inc.update(session, group, incident_type="FLAT", fields={"incident_type"})
    inc.remove(session, group)
    row = inc.ride_incidents(session, r.id)[0]
    assert row["removed"] and rides_svc.ride_row(session, r)["incidents"] == 0
    with pytest.raises(NotFound):           # nothing left to edit until it is restored
        inc.update(session, group, text="x", fields={"text"})
    inc.restore(session, group)
    row = inc.ride_incidents(session, r.id)[0]
    assert not row["removed"] and [a["component_id"] for a in row["affected"]] == [p["rd"].id]


def test_fitting_problem_and_crash_on_the_rider(session):
    b, _ = setup_bike(session)
    r = ride(session, b, "2026-09-10", 120)
    inc.log(session, r.id, incident_type="FIT", affected=["NUMB_HANDS", "NUMB_TOES"])
    inc.log(session, r.id, incident_type="CRASH", affected=["BIKE", "RIDER"])
    rows = inc.ride_incidents(session, r.id)
    assert [a["label"] for a in rows[0]["affected"]] == ["Numb hands", "Numb toes"]
    assert [a["label"] for a in rows[1]["affected"]] == ["Whole bike", "Rider (injury)"]
    assert rides_svc.ride_row(session, r)["incidents"] == 2



def test_bike_lists_its_incidents_open_first(session):
    b, p = setup_bike(session)
    r1 = ride(session, b, "2026-09-10", 60)
    r2 = ride(session, b, "2026-09-12", 40)
    g1 = inc.log(session, r1.id, incident_type="FLAT", affected=[f"c{p['ft'].id}", f"c{p['rt'].id}"])
    g2 = inc.log(session, r2.id, incident_type="SHIFTING", affected=[f"c{p['rd'].id}"], resolved_on="2026-09-12")
    g3 = inc.log(session, r2.id, incident_type="FIT", affected=["NUMB_HANDS"])
    inc.remove(session, g3)
    rows = inc.bike_incidents(session, b.id)
    assert [r["group"] for r in rows] == [g1, g2, g3]          # open, solved, removed
    assert rows[0]["ride_label"].startswith("Ride (2026-09-10") and len(rows[0]["affected"]) == 2
    assert rows[2]["removed"]
