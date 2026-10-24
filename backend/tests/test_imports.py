import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from bikelog.db import make_session_factory
from bikelog.models import Ride, RideSource
from bikelog.services import imports, rides, settings
from bikelog.services import inventory as inv
from bikelog.services.usage import component_usage

CSV = b"""source_id,date,distance_km,duration_min,name,bike,sport_type,trainer
g-1,2026-10-02,60.5,120,Morning,TIME NXR,Ride,no
g-2,2026-10-03T07:30,40,90,Commute,TIME NXR,Ride,no
z-1,2026-10-04T18:00,30,60,Zwift,TIME NXR,VirtualRide,yes
old-1,2026-09-01,99,200,Before start,TIME NXR,Ride,no
bad-1,not-a-date,10,,Broken,TIME NXR,Ride,no
"""


@pytest.fixture()
def world(engine, session):
    b = inv.create_bike(session, name="TIME NXR")
    chain = inv.create_component(session, component_type="CHAIN", label="Chain A", prior_usage="NEW")
    wheel = inv.create_component(session, component_type="REAR_WHEEL", label="Rear wheel", prior_usage="NEW")
    inv.install(session, chain.id, bike_id=b.id, at="2026-09-01")
    inv.install(session, wheel.id, bike_id=b.id, at="2026-09-01")
    settings.set_value(session, "import_start_date", "2026-10-01")
    session.commit()
    return make_session_factory(engine), b, chain, wheel


def run(session, factory, content, **kw):
    session.commit()  # end the test session's transaction (each write takes the SQLite write lock)
    return imports.run_csv_import(factory, content, **kw)


def counts(session):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Ride))


def test_import_respects_start_date_and_reports_errors(session, world):
    factory, b, chain, wheel = world
    res = run(session, factory, CSV, file_name="rides.csv")
    assert res["counts"] == {"CREATED": 3, "SKIPPED_BEFORE_START": 1, "ERROR": 1}
    assert res["errors"][0]["row"] == 6
    session.expire_all()
    assert component_usage(session, chain)["total_km"] == 130.5
    assert component_usage(session, wheel)["total_km"] == 100.5       # Zwift ride: trainer profile


def test_reimport_does_not_duplicate_rides_or_usage(session, world):
    """Acceptance 5."""
    factory, b, chain, _ = world
    run(session, factory, CSV)
    n, total = counts(session), component_usage(session, chain)["total_km"]
    res = run(session, factory, CSV)
    assert res["counts"]["UNCHANGED"] == 3 and "CREATED" not in res["counts"]
    modified = CSV.replace(b"g-1,2026-10-02,60.5", b"g-1,2026-10-02,61.0")   # same identity, new value
    res = run(session, factory, modified)
    assert res["counts"]["UPDATED"] == 1
    assert counts(session) == n
    session.expire_all()
    assert component_usage(session, chain)["total_km"] == pytest.approx(total + 0.5)


def test_source_identity_is_unique_in_database(session, world):
    factory, *_ = world
    run(session, factory, CSV)
    session.expire_all()
    ride_id = session.scalar(select(Ride.id))
    with pytest.raises(IntegrityError):
        session.execute(text("INSERT INTO ride_source (ride_id, source_kind, source_account, source_ref, values_json,"
                             " payload_hash, first_seen_at, last_seen_at) VALUES (:r, 'CSV', 'csv', 'g-1', '{}', 'x',"
                             " 'n', 'n')"), {"r": ride_id + 1000})
    session.rollback()


def test_local_corrections_survive_reimport(session, world):
    factory, b, chain, _ = world
    run(session, factory, CSV)
    session.expire_all()
    rid = session.scalar(select(RideSource.ride_id).where(RideSource.source_ref == "g-1"))
    rides.edit_ride(session, rid, {"distance_km": 55, "name": "Morning (GPS glitch fixed)"})
    session.commit()
    run(session, factory, CSV.replace(b"Morning,", b"Morning ride,"))   # source changed the title
    session.expire_all()
    r = session.get(Ride, rid)
    assert r.distance_km == 55 and r.name == "Morning (GPS glitch fixed)"
    assert component_usage(session, chain)["total_km"] == 125


def test_excluded_imported_ride_does_not_silently_return(session, world):
    factory, b, chain, _ = world
    run(session, factory, CSV)
    session.expire_all()
    rid = session.scalar(select(RideSource.ride_id).where(RideSource.source_ref == "g-2"))
    rides.exclude_ride(session, rid, "test ride")
    session.commit()
    run(session, factory, CSV.replace(b"Commute", b"Commute home"))  # changed at source
    session.expire_all()
    assert session.get(Ride, rid).inclusion == "EXCLUDED"
    assert component_usage(session, chain)["total_km"] == 90.5


def test_interrupted_import_resumes_without_duplicates(session, world):
    factory, b, chain, _ = world
    lines = [b"source_id,date,distance_km,bike"] + [f"r-{i},2026-10-{1 + i % 20:02d},10,TIME NXR".encode()
                                                     for i in range(25)]
    content = b"\n".join(lines) + b"\n"

    def crash(rows_done):
        if rows_done == 10:
            raise RuntimeError("power cut")
    with pytest.raises(RuntimeError):
        run(session, factory, content, chunk_size=5, on_chunk_committed=crash)
    assert counts(session) == 10
    session.commit()
    res = run(session, factory, content, chunk_size=5)
    assert res["resumed"] and res["counts"]["CREATED"] == 25
    assert counts(session) == 25
    session.expire_all()
    assert component_usage(session, chain)["total_km"] == 250
    assert imports.list_batches(session)[0]["status"] == "COMPLETED"


def test_strava_bulk_export_activities_csv(session, world):
    factory, b, chain, _ = world
    content = (b'Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,'
               b'Distance,Max Heart Rate,Relative Effort,Commute,Activity Private Note,Activity Gear,Filename,'
               b'Athlete Weight,Bike Weight,Elapsed Time,Moving Time,Distance\n'
               b'161,"Oct 6, 2026, 7:01:23 AM",First ride,Ride,,5400,45.2,,,false,,TIME NXR,a.fit,,,5400,5000,45200\n'
               b'162,"Oct 7, 2026, 6:00:00 PM",Run,Run,,1800,5.0,,,false,,,b.fit,,,1800,1700,5000\n'
               b'163,"Oct 8, 2026, 6:00:00 PM",Zwift,Virtual Ride,,3600,30.1,,,false,,Unknown bike,c.fit,,,3600,3500,30100\n')
    res = run(session, factory, content)
    assert res["source_kind"] == "STRAVA"
    assert res["counts"] == {"CREATED": 2, "SKIPPED_NOT_CYCLING": 1}
    session.expire_all()
    unknown = session.scalar(select(Ride).where(Ride.name == "Zwift"))
    assert unknown.bike_id is None and unknown.sport_type == "VirtualRide"
    assert any(f["code"] == "NO_BIKE" for f in rides.ride_row(session, unknown)["flags"])
    assert component_usage(session, chain)["total_km"] == pytest.approx(45.2)


def test_unrecognised_csv_is_rejected_clearly(world):
    factory, *_ = world
    with pytest.raises(imports.CsvFormatError, match="Required columns"):
        imports.run_csv_import(factory, b"foo,bar\n1,2\n")


def test_semicolon_and_decimal_comma(session, world):
    factory, b, chain, _ = world
    run(session, factory, "source_id;date;distance_km;bike\nx-1;2026-10-05;1.234,5;TIME NXR\n".encode())
    session.expire_all()
    assert component_usage(session, chain)["total_km"] == pytest.approx(1234.5)
