"""Strava connector logic against an in-memory fake Strava (no network, no credentials).
These tests do NOT prove a live connection works; see DECISIONS.md."""
import pytest
from sqlalchemy import func, select

from bikelog.connectors.strava import sync as strava
from bikelog.connectors.strava.client import StravaTemporaryError
from bikelog.db import make_session_factory
from bikelog.models import Ride
from bikelog.services import inventory as inv
from bikelog.services import rides, settings
from bikelog.services.usage import component_usage

from fake_strava import FakeStrava, act, client_for


@pytest.fixture()
def world(engine, session, tmp_path):
    b = inv.create_bike(session, name="BMC Roadmachine", strava_gear_id="90000001")
    chain = inv.create_component(session, component_type="CHAIN", label="Chain A", prior_usage="NEW")
    inv.install(session, chain.id, bike_id=b.id, at="2026-01-01")
    settings.set_value(session, "import_start_date", "2026-10-01")
    session.commit()
    fake = FakeStrava([act(1, "2026-09-30T10:00:00Z"), act(2, "2026-10-02T08:00:00Z", 50),
                       act(3, "2026-10-03T08:00:00Z", 30), act(4, "2026-10-04T08:00:00Z", 5, sport="Run"),
                       act(5, "2026-10-05T08:00:00Z", 20, gear="b999")])
    return make_session_factory(engine), fake, client_for(fake, tmp_path), chain


def n_rides(session):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Ride))


def test_disabled_by_default(world):
    factory, fake, client, _ = world
    with pytest.raises(RuntimeError, match="disabled"):
        strava.sync(factory, client)


def test_sync_imports_pages_and_is_idempotent(session, world):
    factory, fake, client, chain = world
    res = strava.sync(factory, client, per_page=2, force=True)
    assert res["counts"] == {"CREATED": 3, "SKIPPED_NOT_CYCLING": 1}   # ride 1 before start: not listed
    assert n_rides(session) == 3
    assert component_usage(session, chain)["total_km"] == 80
    session.commit()
    strava.sync(factory, client, per_page=2, force=True, rescan=True)
    assert n_rides(session) == 3 and component_usage(session, chain)["total_km"] == 80
    unknown = session.scalar(select(Ride).where(Ride.distance_km == 20))
    assert unknown.bike_id is None
    session.commit()


def test_interrupted_sync_resumes(session, world):
    factory, fake, client, chain = world
    # calls: page 1, page 2, gear lookup for the unknown bike, then page 3 fails beyond retries
    fake.fail_plan = {4: "net", 5: "net", 6: "net", 7: "net"}
    with pytest.raises(StravaTemporaryError):
        strava.sync(factory, client, per_page=2, force=True)
    first = n_rides(session)
    session.commit()
    strava.sync(factory, client, per_page=2, force=True)
    assert first >= 1 and n_rides(session) == 3
    assert strava.status(session)["last_error"] is None
    session.commit()


def test_disconnect_keeps_all_rides_and_removed_rides_never_come_back(session, world):
    factory, fake, client, chain = world
    strava.sync(factory, client, force=True)
    excluded = session.scalar(select(Ride).where(Ride.distance_km == 30))
    rides.exclude_ride(session, excluded.id, "not my ride")
    session.commit()
    before = n_rides(session)
    session.commit()
    res = strava.mark_disconnected(factory)
    assert res == {"kept_rides": before}
    assert n_rides(session) == before                                   # nothing deleted
    assert component_usage(session, chain)["total_km"] == 50            # removed ride counts nothing
    session.commit()
    strava.sync(factory, client, force=True)                            # reconnect: full re-read
    session.expire_all()
    assert n_rides(session) == before                                   # no duplicates
    assert session.get(Ride, excluded.id).inclusion == "EXCLUDED"       # stays removed
    assert component_usage(session, chain)["total_km"] == 50
    session.commit()


def test_status_never_claims_a_live_connection(session):
    st = strava.status(session)
    assert st["live_connection_verified"] is False and st["blockers"]


def test_unknown_gear_creates_or_links_bike_once(session, engine, tmp_path):
    from bikelog.models import Bike
    inv.create_bike(session, name="Cube SL Road SL")                    # same name, no gear id yet
    session.commit()
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z", 40, gear="b7001"), act(2, "2026-10-03T08:00:00Z", 30, gear="b7001"),
                       act(3, "2026-10-04T08:00:00Z", 20, gear="b7002")],
                      gear={"b7001": {"id": "b7001", "name": "Cannondale Synapse Di2"},
                            "b7002": {"id": "b7002", "name": "Cube SL Road SL"}})
    factory = make_session_factory(engine)
    res = strava.sync(factory, client_for(fake, tmp_path), force=True)
    assert res["counts"]["BIKES_CREATED"] == 1 and res["counts"]["BIKES_LINKED"] == 1
    session.expire_all()
    syn = session.scalar(select(Bike).where(Bike.name == "Cannondale Synapse Di2"))
    cube = session.scalar(select(Bike).where(Bike.name == "Cube SL Road SL"))
    assert syn.strava_gear_id == "7001" and cube.strava_gear_id == "7002"
    assert {r.bike_id for r in session.scalars(select(Ride))} == {syn.id, cube.id}
    st = strava.status(session)
    assert st["live_connection_verified"] is True and st["blockers"] == []   # only after a successful sync
    session.commit()
    again = strava.sync(factory, client_for(fake, tmp_path), force=True, rescan=True)
    assert "BIKES_CREATED" not in again["counts"]
    assert session.scalar(select(func.count()).select_from(Bike)) == 2


def test_sync_command_without_connection_explains_next_step(tmp_path, capsys):
    from bikelog.launcher import main
    assert main(["--data-dir", str(tmp_path / "d"), "--strava-sync", "--no-browser"]) == 2
    assert "--strava-connect" in capsys.readouterr().err
    assert not (tmp_path / "d" / "strava.env").exists()


def test_bike_override_survives_resync_and_strava_gear_changes_are_picked_up(session, world):
    factory, fake, client, chain = world
    other = inv.create_bike(session, name="TIME NXR", strava_gear_id="90000002")
    session.commit()
    strava.sync(factory, client, force=True)
    r2 = session.scalar(select(Ride).where(Ride.distance_km == 50))          # Strava says BMC
    r3 = session.scalar(select(Ride).where(Ride.distance_km == 30))
    res = rides.assign_bike(session, [r2.id], other.id)                     # Strava had the wrong bike
    assert res == {"changed": 1, "rides": 1}
    row = rides.ride_row(session, r2)
    assert row["bike"] == "TIME NXR" and row["bike_overridden"] and row["source_bike"] == "BMC Roadmachine"
    session.commit()
    # later, on Strava: gear of ride 3 corrected to the TIME; ride 2 also edited on Strava
    fake.activities[10_000_003]["gear_id"] = "b90000002"
    fake.activities[10_000_002]["name"] = "Renamed on Strava"
    fake.now += 20 * 24 * 3600
    session.commit()
    strava.sync(factory, client, force=True)                                # incremental, 30-day look-back
    session.expire_all()
    assert session.get(Ride, r3.id).bike_id == other.id                     # gear change picked up
    r2 = session.get(Ride, r2.id)
    assert r2.bike_id == other.id and r2.name == "Renamed on Strava"        # override kept, rest updated
    session.commit()
    strava.sync(factory, client, rescan=True, force=True)                   # Re-read keeps it too
    session.expire_all()
    assert session.get(Ride, r2.id).bike_id == other.id
    # setting it back to Strava's bike removes the override
    r2 = session.get(Ride, r2.id)
    rides.assign_bike(session, [r2.id], rides.ride_row(session, r2)["source_bike_id"])
    assert not rides.ride_row(session, r2)["bike_overridden"]
    # remove the assignment (no bike): kept across re-sync
    rides.assign_bike(session, [r2.id], None)
    session.commit()
    strava.sync(factory, client, rescan=True, force=True)
    session.expire_all()
    r2 = session.get(Ride, r2.id)
    assert r2.bike_id is None and rides.ride_row(session, r2)["bike_overridden"]
    session.commit()


def test_manual_ride_bike_can_be_removed(session, world):
    b = inv.get_bike(session, 1)
    r = rides.add_manual_ride(session, bike_id=b.id, when="2026-10-06", distance=10)
    rides.edit_ride(session, r.id, {"bike_id": None})
    assert r.bike_id is None
    rides.assign_bike(session, [r.id], b.id)
    assert r.bike_id == b.id
    session.commit()


def test_removed_rides_view(session, world):
    factory, fake, client, chain = world
    strava.sync(factory, client, force=True)
    r = session.scalar(select(Ride).where(Ride.distance_km == 30))
    rides.exclude_ride(session, r.id, "not my ride")
    removed = rides.list_rides(session, view="removed")
    active = rides.list_rides(session, view="active")
    assert [x["id"] for x in removed] == [r.id] and removed[0]["removed"]
    assert r.id not in {x["id"] for x in active}
    session.commit()


def test_deleted_strava_bike_is_not_created_again(session, engine, tmp_path):
    from bikelog.models import Bike
    from bikelog.services import settings
    settings.set_value(session, "strava_ignored_gear", '["7001"]', internal=True)   # as after deleting it
    session.commit()
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z", 40, gear="b7001")],
                      gear={"b7001": {"id": "b7001", "name": "Cannondale Synapse Di2"}})
    res = strava.sync(make_session_factory(engine), client_for(fake, tmp_path), force=True)
    session.expire_all()
    assert "BIKES_CREATED" not in res["counts"]
    assert session.scalar(select(func.count()).select_from(Bike)) == 0
    assert [r.bike_id for r in session.scalars(select(Ride))] == [None]   # the ride still comes in, without a bike
