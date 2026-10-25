"""Ride incidents (flat, crash, defect) linked to the ride and the affected part; dry/wet per ride."""
import pytest

from bikelog.services import inventory as inv
from bikelog.services import journal
from bikelog.services import rides as rides_svc
from bikelog.services.errors import DomainError

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
