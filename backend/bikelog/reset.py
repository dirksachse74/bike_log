"""Fresh start and restore while the app runs (Settings → Fresh start / Backups).

Nothing is lost: both first write a backup that is kept (never pruned), and that backup can be restored
from Settings. The database file stays in place (no rename/delete of an open file, which Windows
refuses); its contents are replaced through SQLite itself:

* reset: drop every table, view and trigger in one exclusive transaction (DROP TABLE does not fire the
  no-delete triggers), then run all migrations again and add the default service rules.
* restore: copy a backup into the live database with SQLite's backup API, then migrate it to the
  current schema if it is older.
Strava app details and login live in ``strava.env``, not in the database; a reset keeps them unless
asked to clear them.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session, sessionmaker

from bikelog.backup import KEPT_MARK, backup_database
from bikelog.db import session_scope
from bikelog.migrate import alembic_config
from bikelog.paths import DataPaths
from bikelog.services.errors import DomainError

log = logging.getLogger(__name__)

CONFIRM_WORD = "RESET"
_lock = threading.Lock()


def _migrate_and_seed(factory: sessionmaker[Session]) -> None:
    engine = factory.kw["bind"]
    engine.dispose()          # pooled connections may have cached the old schema
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    from bikelog.services.reference import ensure_reference_data
    with session_scope(factory) as s:
        ensure_reference_data(s)


def _keep_strava_connection(factory: sessionmaker[Session], connected: bool) -> None:
    if not connected:
        return
    from bikelog.connectors.strava.sync import SOURCE_ACCOUNT
    from bikelog.models import StravaConnection
    with session_scope(factory) as s:
        s.add(StravaConnection(athlete_id=SOURCE_ACCOUNT, status="ACTIVE"))


def reset_database(factory: sessionmaker[Session], paths: DataPaths, *, confirm: str, clear_strava: bool = False,
                   strava_web=None) -> dict:
    if (confirm or "").strip() != CONFIRM_WORD:
        raise DomainError(f"Type {CONFIRM_WORD} to confirm the fresh start")
    if strava_web is not None and strava_web.job.get("running"):
        raise DomainError("A Strava sync is running; wait until it has finished")
    with _lock:
        backup = backup_database(paths, f"{KEPT_MARK}reset")
        engine = factory.kw["bind"]
        engine.dispose()
        raw = sqlite3.connect(paths.database, isolation_level=None, timeout=10)
        with closing(raw):
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute("BEGIN EXCLUSIVE")
            try:
                objects = raw.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                                      "AND type IN ('trigger', 'view', 'table')").fetchall()
                for kind in ("trigger", "view", "table"):
                    for t, name in objects:
                        if t == kind:
                            raw.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
                raw.execute("COMMIT")
            except Exception:
                raw.execute("ROLLBACK")
                raise
            raw.execute("VACUUM")
        _migrate_and_seed(factory)
        strava = _strava_after_reset(factory, strava_web, clear_strava)
    log.warning("Database reset (fresh start); kept backup %s; Strava %s", backup.name if backup else None,
                "cleared" if clear_strava else "kept")
    return {"backup": backup.name if backup else None, "backup_path": str(backup) if backup else None,
            "strava": strava}


def _strava_after_reset(factory: sessionmaker[Session], strava_web, clear: bool) -> str:
    if strava_web is None:
        return "not set up"
    env = strava_web._env()
    has_login = bool(env.get("STRAVA_REFRESH_TOKEN"))
    if clear:
        if has_login:
            try:
                strava_web.client().deauthorize()
            except Exception as e:  # offline or token expired: the local login is removed anyway
                log.warning("Strava deauthorize during reset failed: %s", e)
        from bikelog.connectors.strava import client as sc
        sc.update_env(strava_web.env_file, {k: None for k in env if k.startswith("STRAVA_")})
        return "cleared"
    _keep_strava_connection(factory, has_login)
    return "kept (connected)" if has_login else ("kept (app details only)" if env.get("STRAVA_CLIENT_ID") else
                                                 "not set up")


def _backup_file(paths: DataPaths, name: str) -> Path:
    f = (paths.backups / name).resolve()
    if f.parent != paths.backups.resolve() or not f.name.endswith(".db") or not f.exists():
        raise DomainError("No such backup")
    return f


def restore_backup(factory: sessionmaker[Session], paths: DataPaths, name: str, strava_web=None) -> dict:
    src = _backup_file(paths, name)
    if strava_web is not None and strava_web.job.get("running"):
        raise DomainError("A Strava sync is running; wait until it has finished")
    with closing(sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)) as c:
        try:
            ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except sqlite3.DatabaseError:
            ok = False
        if not ok:
            raise DomainError(f"{name} is damaged or not a database; pick another backup")
        try:
            rev = c.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.Error:
            rev = None
    known = {s.revision for s in ScriptDirectory.from_config(alembic_config()).walk_revisions()}
    if rev is None or rev[0] not in known:
        raise DomainError(f"{name} is not a Bike Log database this version can read")
    with _lock:
        safety = backup_database(paths, f"{KEPT_MARK}restore")
        engine = factory.kw["bind"]
        engine.dispose()
        with closing(sqlite3.connect(src)) as s, closing(sqlite3.connect(paths.database, timeout=10)) as d:
            s.backup(d)
        _migrate_and_seed(factory)
    log.warning("Restored backup %s (backup of the data before: %s)", name, safety.name if safety else None)
    return {"restored": name, "backup": safety.name if safety else None,
            "backup_path": str(safety) if safety else None}
