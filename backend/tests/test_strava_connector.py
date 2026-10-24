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
    fake.fail_plan = {3: "net", 4: "net", 5: "net", 6: "net"}   # second page fails beyond retries
    with pytest.raises(StravaTemporaryError):
        strava.sync(factory, client, per_page=2, force=True)
    first = n_rides(session)
    session.commit()
    strava.sync(factory, client, per_page=2, force=True)
    assert first >= 1 and n_rides(session) == 3
    assert strava.status(session)["last_error"] is None
    session.commit()


def test_disconnect_deletes_imported_data_but_keeps_exclusions(session, world):
    factory, fake, client, chain = world
    strava.sync(factory, client, force=True)
    excluded = session.scalar(select(Ride).where(Ride.distance_km == 30))
    rides.exclude_ride(session, excluded.id, "not my ride")
    manual = rides.add_manual_ride(session, bike_id=inv.get_bike(session, 1).id, when="2026-10-06", distance=10)
    session.commit()
    res = strava.delete_imported(factory)
    assert res == {"deleted_rides": 2, "kept_exclusion_identities": 1}
    assert component_usage(session, chain)["total_km"] == 10            # manual ride still counts
    session.commit()
    strava.sync(factory, client, force=True)                            # reconnect
    session.expire_all()
    assert session.get(Ride, excluded.id).inclusion == "EXCLUDED"
    assert component_usage(session, chain)["total_km"] == 60
    assert manual.id
    session.commit()


def test_status_never_claims_a_live_connection(session):
    st = strava.status(session)
    assert st["live_connection_verified"] is False and st["blockers"]
