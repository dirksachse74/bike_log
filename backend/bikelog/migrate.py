"""Apply Alembic migrations at startup, taking a backup first whenever the schema changes."""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from bikelog.backup import backup_database
from bikelog.paths import DataPaths, resource_root

log = logging.getLogger(__name__)


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resource_root() / "migrations"))
    return cfg


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def upgrade_database(engine: Engine, paths: DataPaths) -> dict:
    """Bring the database to head. Returns what happened, for the log and diagnostics."""
    head = head_revision()
    db_existed = paths.database.exists() and paths.database.stat().st_size > 0
    current = current_revision(engine) if db_existed else None
    if current == head:
        return {"from": current, "to": head, "backup": None}
    known = {s.revision for s in ScriptDirectory.from_config(alembic_config()).walk_revisions()}
    if current is not None and current not in known:
        raise RuntimeError(
            f"Database schema revision {current} is newer than this app version knows (head {head}). "
            "Install the newer Bike Log version or restore an older backup."
        )
    backup = backup_database(paths, f"pre-upgrade-{current or 'empty'}-to-{head}") if db_existed else None
    log.info("Migrating database from %s to %s", current, head)
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return {"from": current, "to": head, "backup": backup.name if backup else None}
