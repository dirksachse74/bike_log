"""Sample database: added only when the app creates a new database; never touches existing data; flagged
until Fresh start removes it."""
from datetime import date

import pytest
from sqlalchemy import func, select

from bikelog import launcher, reset
from bikelog.models import Bike, ChangeLog, JournalEntry, Ride
from bikelog.paths import DataPaths
from bikelog.services import demo, inventory as inv, maintenance as m, usage
from bikelog.services.errors import Protected

from helpers import bike


def count(factory, model):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_new_database_gets_sample_data_existing_one_never(tmp_path):
    paths = DataPaths(tmp_path / "data").ensure()
    engine, factory, _ = launcher.prepare(paths, sample=True)
    with factory() as s:
        assert demo.is_sample(s)
        names = {b.name for b in s.scalars(select(Bike))}
        assert names == {"Aurora SL", "Winter Allroad"}
        assert s.scalar(select(func.count()).select_from(Ride)) > 15
        incidents = {e.incident_type for e in s.scalars(select(JournalEntry)) if e.incident_type}
        assert incidents == {"FLAT", "CRASH", "DEFECT"}
        sources = set(s.scalars(select(ChangeLog.source).distinct()))
        assert sources == {"SAMPLE"}
    engine.dispose()
    with factory() as s:      # second start: the file exists, nothing is added again
        before = s.scalar(select(func.count()).select_from(Ride))
    engine2, factory2, _ = launcher.prepare(paths, sample=True)
    assert count(factory2, Ride) == before
    engine2.dispose()


def test_existing_personal_database_is_never_seeded(engine, paths, session):
    bike(session, "My bike")
    session.commit()
    _, factory, _ = launcher.prepare(paths, sample=True)
    assert count(factory, Bike) == 1
    with factory() as s:
        assert not demo.is_sample(s)
        with pytest.raises(Protected):
            demo.seed_sample(s)


def test_sample_numbers_add_up_and_fresh_start_removes_it(tmp_path):
    paths = DataPaths(tmp_path / "data").ensure()
    engine, factory, _ = launcher.prepare(paths, sample=True)
    with factory() as s:
        aurora = s.scalar(select(Bike).where(Bike.name == "Aurora SL"))
        u = usage.bike_usage(s, aurora)
        ride_km = s.scalar(select(func.sum(Ride.distance_km)).where(Ride.bike_id == aurora.id))
        assert u["total_km"] == pytest.approx(850 + ride_km) and u["certainty"] == "ESTIMATED"
        winter = s.scalar(select(Bike).where(Bike.name == "Winter Allroad"))
        assert "ATTENTION_CRASH" in {r["rule_code"] for r in m.bike_attention_items(s, winter)}
        assert inv.shifting_of(s, aurora) == "ELECTRONIC"
    reset.reset_database(factory, paths, confirm="RESET")
    with factory() as s:
        assert not demo.is_sample(s) and s.scalar(select(func.count()).select_from(Bike)) == 0
    engine.dispose()


def test_sample_is_the_same_every_time():
    import pathlib
    import tempfile

    from bikelog.db import make_engine, make_session_factory, session_scope
    from bikelog.migrate import upgrade_database
    from bikelog.services.reference import ensure_reference_data
    totals = []
    for _ in range(2):
        paths = DataPaths(pathlib.Path(tempfile.mkdtemp()) / "d").ensure()
        eng = make_engine(paths.database)
        upgrade_database(eng, paths)
        f = make_session_factory(eng)
        with session_scope(f) as s:
            ensure_reference_data(s)
            demo.seed_sample(s, date(2026, 10, 26))
        with f() as s:
            totals.append(sorted((r.ride_date, r.distance_km) for r in s.scalars(select(Ride))))
        eng.dispose()
    assert totals[0] == totals[1]
