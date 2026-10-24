from __future__ import annotations

import pytest

from bikelog.db import make_engine, make_session_factory
from bikelog.migrate import upgrade_database
from bikelog.paths import DataPaths
from bikelog.services.reference import ensure_reference_data


@pytest.fixture()
def paths(tmp_path) -> DataPaths:
    return DataPaths(tmp_path / "data").ensure()


@pytest.fixture()
def engine(paths):
    eng = make_engine(paths.database)
    upgrade_database(eng, paths)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    factory = make_session_factory(engine)
    s = factory()
    ensure_reference_data(s)
    s.commit()
    yield s
    s.rollback()
    s.close()
