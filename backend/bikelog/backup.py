"""Backups, export and restore.

* Backups are consistent SQLite snapshots (online backup API), safe while the app runs.
* An export is a zip with manifest.json, the database snapshot and all attachments,
  so it can be restored on another machine. Stable IDs (uuid columns) travel with it.
* Restore validates the archive, snapshots the current data first, then swaps files.
  It only runs while the server is stopped (see launcher --restore).
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from bikelog import __version__, buildinfo
from bikelog.paths import DataPaths

log = logging.getLogger(__name__)

EXPORT_FORMAT = 1
KEEP_AUTO_BACKUPS = 10
KEPT_MARK = "kept-before-"   # backups with this in the name (fresh start, restore) are never pruned


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def snapshot_database(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3's own context manager does not close connections; an open handle would keep -wal/-shm alive
    with closing(sqlite3.connect(src)) as s, closing(sqlite3.connect(dest)) as d:
        s.backup(d)
    with closing(sqlite3.connect(dest)) as d:
        d.execute("PRAGMA journal_mode = DELETE")  # self-contained single file, no -wal needed to read it
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise RuntimeError(f"Backup integrity check failed for {dest}: {ok}")
    return dest


def backup_database(paths: DataPaths, reason: str) -> Path | None:
    """Snapshot the live database into backups/. Returns None if there is no database yet."""
    if not paths.database.exists():
        return None
    dest = paths.backups / f"bikelog-{_stamp()}-{reason}.db"
    snapshot_database(paths.database, dest)
    log.info("Database backup written: %s", dest.name)
    prune_backups(paths)
    return dest


def prune_backups(paths: DataPaths, keep: int = KEEP_AUTO_BACKUPS) -> None:
    files = sorted((p for p in paths.backups.glob("bikelog-*.db") if KEPT_MARK not in p.name),
                   key=lambda p: p.name, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


def store_uploaded_backup(paths: DataPaths, data: bytes, file_name: str | None = None) -> dict:
    """Save an uploaded database backup into backups/ after checking it is a sound SQLite database with a
    Bike Log schema. Restoring it is a separate step (reset.restore_backup), which writes a safety backup first."""
    from bikelog.services.errors import DomainError
    if not data:
        raise DomainError("The file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DomainError("The file is larger than 1 GB; that is not a Bike Log backup")
    if not data.startswith(b"SQLite format 3\x00"):
        raise DomainError("This is not a Bike Log backup file (pick a bikelog-....db file)")
    dest = paths.backups / f"bikelog-{_stamp()}-uploaded.db"
    paths.backups.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    try:
        with closing(sqlite3.connect(f"file:{tmp.as_posix()}?mode=ro", uri=True)) as c:
            ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            has_schema = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'").fetchone()
    except sqlite3.DatabaseError:
        ok, has_schema = False, None
    if not ok or not has_schema:
        tmp.unlink(missing_ok=True)
        raise DomainError("This file is damaged or not a Bike Log database")
    tmp.replace(dest)
    log.info("Backup uploaded%s: %s", f" from {file_name}" if file_name else "", dest.name)
    return {"name": dest.name, "size": len(data)}


def export_archive(paths: DataPaths, schema_revision: str | None, dest: Path | None = None) -> Path:
    dest = dest or paths.exports / f"bikelog-export-{_stamp()}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        snap = snapshot_database(paths.database, Path(tmp) / "bikelog.db")
        manifest = {
            "format": EXPORT_FORMAT,
            "app_version": __version__, "app_build": buildinfo.full_version(),
            "schema_revision": schema_revision,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.write(snap, "bikelog.db")
            for f in sorted(paths.attachments.rglob("*")):
                if f.is_file():
                    z.write(f, "attachments/" + f.relative_to(paths.attachments).as_posix())
    log.info("Export written: %s", dest.name)
    return dest


def read_manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        if "manifest.json" not in names or "bikelog.db" not in names:
            raise ValueError("Not a Bike Log export: manifest.json or bikelog.db missing")
        manifest = json.loads(z.read("manifest.json"))
        for n in names:  # refuse path traversal
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError(f"Unsafe path in archive: {n}")
    if manifest.get("format") != EXPORT_FORMAT:
        raise ValueError(f"Unsupported export format {manifest.get('format')}")
    return manifest


def restore_archive(paths: DataPaths, archive: Path) -> dict:
    """Replace database and attachments with the archive's. Server must be stopped."""
    manifest = read_manifest(archive)
    safety = backup_database(paths, "pre-restore")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmpdir)
        with closing(sqlite3.connect(tmpdir / "bikelog.db")) as c:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database in archive failed integrity check")
        for suffix in ("-wal", "-shm"):
            Path(str(paths.database) + suffix).unlink(missing_ok=True)
        shutil.copy2(tmpdir / "bikelog.db", paths.database)
        if paths.attachments.exists():
            old = paths.backups / f"attachments-{_stamp()}-pre-restore"
            shutil.move(str(paths.attachments), old)
        src_att = tmpdir / "attachments"
        if src_att.exists():
            shutil.copytree(src_att, paths.attachments)
        else:
            paths.attachments.mkdir(parents=True, exist_ok=True)
    log.info("Restored export from %s (safety backup: %s)", archive.name, safety.name if safety else "none")
    return manifest
