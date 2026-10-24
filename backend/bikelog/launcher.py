"""Single launcher: `bikelog` (or BikeLog.exe). Starts the local server on 127.0.0.1 and opens the browser.

User data lives in the per-user data directory (see paths.py), never next to the program:
  Windows  %LOCALAPPDATA%\\BikeLog      Linux  ~/.local/share/bikelog      override  --data-dir / BIKELOG_DATA_DIR
Demo mode (--demo) uses a separate "demo" data directory with sample data and never touches personal data.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from bikelog import __version__
from bikelog.backup import backup_database, export_archive, restore_archive
from bikelog.db import make_engine, make_session_factory, session_scope
from bikelog.logging_setup import setup_logging
from bikelog.migrate import head_revision, upgrade_database
from bikelog.paths import DataPaths, default_data_dir
from bikelog.single_instance import AlreadyRunning, InstanceLock

log = logging.getLogger("bikelog")
DEFAULT_PORT = 8765
DAILY_BACKUP_S = 24 * 3600


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if sys.platform != "win32":  # like uvicorn; otherwise a restart finds the port in TIME_WAIT
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port")


def _wait_and_open(url: str, open_browser: bool) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "api/health", timeout=1) as r:
                if r.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    log.info("Bike Log is running at %s", url)
    print(f"Bike Log {__version__} is running at {url}  (close this window or press Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)


def _daily_backup(paths: DataPaths) -> None:
    latest = max((p.stat().st_mtime for p in paths.backups.glob("bikelog-*.db")), default=0)
    if paths.database.exists() and time.time() - latest > DAILY_BACKUP_S:
        backup_database(paths, "daily")


def prepare(paths: DataPaths, *, demo: bool = False):
    """Open (and if needed migrate) the database. Returns (engine, session factory, migration info)."""
    engine = make_engine(paths.database)
    info = upgrade_database(engine, paths)
    factory = make_session_factory(engine)
    from bikelog.services import demo as demo_svc
    from bikelog.services.reference import ensure_reference_data
    with session_scope(factory) as s:
        ensure_reference_data(s)
        if demo:
            demo_svc.mark_demo_database(s)
            demo_svc.seed(s)
    return engine, factory, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bikelog", description="Bike Log: local bike maintenance log")
    ap.add_argument("--data-dir", type=Path, help="data directory (default: per-user app data)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("BIKELOG_PORT", DEFAULT_PORT)))
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--demo", action="store_true", help="start with sample data in a separate demo data directory")
    ap.add_argument("--backup", action="store_true", help="write a database backup and exit")
    ap.add_argument("--export", type=Path, nargs="?", const=Path(), help="write a full export (zip) and exit")
    ap.add_argument("--restore", type=Path, help="restore a full export (zip) and exit (app must be closed)")
    ap.add_argument("--version", action="version", version=f"Bike Log {__version__} (schema {head_revision()})")
    args = ap.parse_args(argv)

    root = args.data_dir.expanduser().resolve() if args.data_dir else default_data_dir()
    if args.demo:
        root = root / "demo"
    paths = DataPaths(root).ensure()
    setup_logging(paths.logs)
    log.info("Bike Log %s starting; data directory %s", __version__, paths.root)

    lock = InstanceLock(paths.lock_file, paths.instance_file)
    try:
        lock.acquire()
    except AlreadyRunning as e:
        url = e.info.get("url")
        if args.backup or args.export is not None or args.restore:
            print("Bike Log is running; close it first.", file=sys.stderr)
            return 2
        print(f"Bike Log is already running{' at ' + url if url else ''}.")
        if url and not args.no_browser:
            webbrowser.open(url)
        return 0
    try:
        if args.restore:
            manifest = restore_archive(paths, args.restore)
            print(f"Restored export from {manifest.get('created_at')}. A safety backup of the previous data is in "
                  f"{paths.backups}.")
            return 0
        engine, factory, info = prepare(paths, demo=args.demo)
        if info["backup"]:
            log.info("Upgraded schema %s -> %s; pre-upgrade backup %s", info["from"], info["to"], info["backup"])
        if args.backup:
            dest = backup_database(paths, "manual")
            print(f"Backup written: {dest}")
            return 0
        if args.export is not None:
            dest = export_archive(paths, head_revision(), (args.export if str(args.export) not in ("", ".") else None))
            print(f"Export written: {dest}")
            return 0
        _daily_backup(paths)

        import uvicorn

        from bikelog.api.app import create_app
        token = os.environ.get("BIKELOG_DEV_TOKEN") or None
        app = create_app(factory, paths, token=token)
        port = _free_port(args.port)
        url = f"http://127.0.0.1:{port}/"
        lock.publish(url)
        threading.Thread(target=_wait_and_open, args=(url, not args.no_browser), daemon=True).start()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, loop="asyncio", http="h11", log_config=None,
                                access_log=False)
        uvicorn.Server(config).run()
        engine.dispose()
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
