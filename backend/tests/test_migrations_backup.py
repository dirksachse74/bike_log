"""Acceptance 7: a database upgrade preserves existing records. Plus backup/restore and schema drift."""
import sqlite3

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select

from bikelog.backup import backup_database, export_archive, read_manifest, restore_archive
from bikelog.db import make_engine, make_session_factory
from bikelog.migrate import alembic_config, current_revision, head_revision, upgrade_database
from bikelog.models import Base, Component, Ride
from bikelog.paths import DataPaths
from bikelog.services import inventory as inv
from bikelog.services import rides
from bikelog.services.reference import ensure_reference_data
from bikelog.services.usage import component_usage


def _upgrade_to(engine, rev):
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, rev)


def test_upgrade_from_first_release_preserves_records(tmp_path):
    paths = DataPaths(tmp_path / "d").ensure()
    eng = make_engine(paths.database)
    _upgrade_to(eng, "0001")                      # database as created by the first schema version
    raw = sqlite3.connect(paths.database)
    raw.executescript("""
        INSERT INTO bike (id, uuid, name, status, created_at, updated_at) VALUES (1, 'b-1', 'TIME NXR', 'ACTIVE', 'x', 'x');
        INSERT INTO component (id, uuid, component_type, label, prior_usage, status, created_at, updated_at)
            VALUES (1, 'c-1', 'CHAIN', 'Chain A', 'NEW', 'ACTIVE', 'x', 'x');
        INSERT INTO installation (uuid, component_id, bike_id, slot, installed_at, installed_utc, created_at)
            VALUES ('i-1', 1, 1, 'CHAIN', '2026-10-01', '2026-09-30T22:00:00Z', 'x');
        INSERT INTO ride (id, uuid, bike_id, ride_date, sort_utc, distance_km, sport_type, source_kind, status,
                          inclusion, assignment_uncertain, created_at, updated_at)
            VALUES (1, 'r-1', 1, '2026-10-02', '2026-10-01T22:00:00Z', 42.0, 'Ride', 'MANUAL', 'ACTIVE', 'INCLUDED', 0, 'x', 'x');
        INSERT INTO usage_contribution (ride_id, component_id, bike_id, slot, sort_utc, km, basis, certain, state)
            VALUES (1, 1, 1, 'CHAIN', '2026-10-01T22:00:00Z', 42.0, 'HISTORY', 1, 'COUNTED');
    """)
    raw.commit()
    raw.close()
    assert current_revision(eng) == "0001"
    info = upgrade_database(eng, paths)
    assert info["from"] == "0001" and info["to"] == head_revision() and info["backup"]
    assert (paths.backups / info["backup"]).exists()             # backup taken before the schema change
    s = make_session_factory(eng)()
    chain = s.get(Component, 1)
    assert chain.label == "Chain A" and chain.uuid == "c-1" and chain.specs_json == "{}"
    assert s.get(Ride, 1).distance_km == 42.0
    assert component_usage(s, chain)["total_km"] == 42.0
    ensure_reference_data(s)
    rides.add_manual_ride(s, bike_id=1, when="2026-10-03", distance=8)   # app works on the upgraded DB
    assert component_usage(s, chain)["total_km"] == 50.0
    s.commit()
    s.close()
    assert upgrade_database(eng, paths)["backup"] is None          # second start: nothing to do


def test_models_match_migrations(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_backup_export_restore_roundtrip(tmp_path, engine, paths):
    s = make_session_factory(engine)()
    ensure_reference_data(s)
    b = inv.create_bike(s, name="Cube")
    s.commit()
    snap = backup_database(paths, "manual")
    assert snap and snap.exists()
    archive = export_archive(paths, head_revision())
    assert read_manifest(archive)["schema_revision"] == head_revision()
    inv.create_bike(s, name="Added after export")
    s.commit()
    s.close()
    engine.dispose()
    restore_archive(paths, archive)
    eng2 = make_engine(paths.database)
    s2 = make_session_factory(eng2)()
    names = set(s2.scalars(select(inv.Bike.name)))
    assert names == {"Cube"} and b.uuid == s2.scalar(select(inv.Bike.uuid))
    assert any(p.name.endswith("pre-restore.db") for p in paths.backups.iterdir())
    s2.close()
    eng2.dispose()
