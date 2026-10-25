"""Single launcher: `bikelog` (or BikeLog.exe). Starts the local server on 127.0.0.1 and opens the browser.

User data lives in the per-user data directory (see paths.py), never next to the program:
  Windows  %LOCALAPPDATA%\\BikeLog      Linux  ~/.local/share/bikelog      override  --data-dir / BIKELOG_DATA_DIR
Demo mode (--demo) uses a separate "demo" data directory with sample data and never touches personal data.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from bikelog import buildinfo
from bikelog.backup import backup_database, export_archive, restore_archive
from bikelog.db import make_engine, make_session_factory, session_scope
from bikelog.logging_setup import setup_logging
from bikelog.migrate import head_revision, upgrade_database
from bikelog.paths import DataPaths, default_data_dir
from bikelog.single_instance import AlreadyRunning, InstanceLock

log = logging.getLogger("bikelog")
DEFAULT_PORT = 8765
DAILY_BACKUP_S = 24 * 3600
STRAVA_OAUTH_PORT = 8766  # Strava app setting "Authorization Callback Domain" must be: localhost


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
    print(f"Bike Log {buildinfo.full_version()} is running at {url}  (close this window or press Ctrl+C to stop)", flush=True)
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
    ap.add_argument("--strava-connect", action="store_true",
                    help="connect your Strava account (asks for the API app id/secret once) and exit")
    ap.add_argument("--strava-sync", action="store_true", help="import rides from Strava and exit")
    ap.add_argument("--strava-rescan", action="store_true", help="with --strava-sync: re-read all rides since the start date")
    ap.add_argument("--strava-disconnect", action="store_true",
                    help="revoke Strava access and delete rides imported from the Strava API, then exit")
    ap.add_argument("--import-products", type=Path, nargs="+", metavar="FILE",
                    help="import product JSON files (see docs/product-import.md) and exit")
    ap.add_argument("--dry-run", action="store_true", help="with --import-products: check only, write nothing")
    ap.add_argument("--write-product-templates", type=Path, metavar="DIR",
                    help="write the JSON schema and example for every part type into DIR and exit")
    ap.add_argument("--version", action="version", version=f"Bike Log {buildinfo.full_version()} (schema {head_revision()}, commit {buildinfo.commit()})")
    args = ap.parse_args(argv)

    if args.write_product_templates:
        return _write_templates(args.write_product_templates)
    root = args.data_dir.expanduser().resolve() if args.data_dir else default_data_dir()
    if args.demo:
        root = root / "demo"
    paths = DataPaths(root).ensure()
    setup_logging(paths.logs)
    log.info("Bike Log %s (commit %s) starting; data directory %s", buildinfo.full_version(), buildinfo.commit(),
             paths.root)

    lock = InstanceLock(paths.lock_file, paths.instance_file)
    try:
        lock.acquire()
    except AlreadyRunning as e:
        url = e.info.get("url")
        if args.backup or args.export is not None or args.restore or _strava_cmd(args) or args.import_products:
            print("Bike Log is running; close it first.", file=sys.stderr)
            return 2
        print(f"Bike Log is already running{' at ' + url if url else ''}.")
        running = e.info.get("commit")
        if running and running != buildinfo.commit():
            print(f"WARNING: the running copy is an older or different version ({running}); this one is "
                  f"{buildinfo.commit()}. Close the other Bike Log window (or end BikeLog.exe in Task Manager) "
                  "and start Bike Log again.")
            log.warning("second start: running copy %s differs from this copy %s", running, buildinfo.commit())
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
        if _strava_cmd(args):
            return _strava(args, paths, factory)
        if args.import_products:
            return _import_products(args.import_products, factory, dry_run=args.dry_run, paths=paths)
        _daily_backup(paths)

        import uvicorn

        from bikelog.api.app import create_app
        token = os.environ.get("BIKELOG_DEV_TOKEN") or None
        app = create_app(factory, paths, token=token)
        port = _free_port(args.port)
        url = f"http://127.0.0.1:{port}/"
        lock.publish(url, version=buildinfo.full_version(), commit=buildinfo.commit())
        threading.Thread(target=_wait_and_open, args=(url, not args.no_browser), daemon=True).start()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, loop="asyncio", http="h11", log_config=None,
                                access_log=False)
        uvicorn.Server(config).run()
        engine.dispose()
        return 0
    finally:
        lock.release()


def _write_templates(folder: Path) -> int:
    from bikelog.services import product_import
    folder.mkdir(parents=True, exist_ok=True)
    for t in product_import.templates():
        code = t["component_type"]
        for kind, fn in (("schema", product_import.schema), ("example", product_import.example)):
            (folder / f"{code.lower()}.{kind}.json").write_text(
                json.dumps(fn(code), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "AGENT_INSTRUCTIONS.md").write_text(product_import.agent_instructions(), encoding="utf-8")
    print(f"Templates written to {folder}")
    return 0


def _import_products(files: list[Path], factory, *, dry_run: bool, paths: DataPaths) -> int:
    """Import product JSON files one by one; each file is all-or-nothing. Exit code 1 if any file failed."""
    from bikelog.services import product_import
    from bikelog.services.errors import DomainError
    if not dry_run:
        print(f"Backup written: {backup_database(paths, 'pre-product-import')}")
    failed = 0
    for f in files:
        try:
            report = product_import.run_import(factory, f.read_bytes(), dry_run=dry_run)
        except (OSError, DomainError) as e:
            print(f"{f}: {e}", file=sys.stderr)
            failed += 1
            continue
        for w in report["warnings"]:
            print(f"{f}: warning: {w}")
        if not report["ok"]:
            failed += 1
            for e in report["errors"]:
                print(f"{f}: error: {e}", file=sys.stderr)
            print(f"{f}: nothing imported", file=sys.stderr)
            continue
        c = report["counts"]
        print(f"{f}: {'check only, ' if dry_run else ''}{c['CREATED']} new, {c['UPDATED']} updated, "
              f"{c['UNCHANGED']} unchanged products; {c['ITEMS_CREATED']} new and {c['ITEMS_EXISTING']} existing items")
    return 1 if failed else 0


def _strava_cmd(args) -> bool:
    return bool(args.strava_connect or args.strava_sync or args.strava_disconnect)


def _strava(args, paths: DataPaths, factory) -> int:
    """Strava commands run with the app closed (they hold the single-instance lock).
    Credentials and tokens live only in <data dir>/strava.env, never in the database."""
    import getpass

    from bikelog.connectors.strava import client as sc
    from bikelog.connectors.strava import sync as strava
    env_file = paths.root / "strava.env"
    os.environ["BIKELOG_STRAVA_ENV"] = str(env_file)
    try:
        if args.strava_connect:
            env = sc.read_env(env_file)
            if not (env.get("STRAVA_CLIENT_ID") and env.get("STRAVA_CLIENT_SECRET")):
                print("Enter your Strava API application details (strava.com/settings/api).")
                cid = input("Client ID: ").strip()
                secret = getpass.getpass("Client Secret (not shown while typing): ").strip()
                if not cid.isdigit() or not secret:
                    print("Client ID must be a number and the secret must not be empty.", file=sys.stderr)
                    return 2
                sc.update_env(env_file, {"STRAVA_CLIENT_ID": cid, "STRAVA_CLIENT_SECRET": secret})
                print(f"Saved to {env_file} (only on this computer).")
            client = sc.StravaClient(token_store=sc.EnvTokenStore(env_file))
            print("Your browser opens Strava. Click 'Authorize'. Waiting up to 5 minutes...")
            tok = client.authorize_via_localhost(port=STRAVA_OAUTH_PORT, open_browser=not args.no_browser)
            print(f"Strava connected (athlete {tok['athlete_id']}, scope {tok.get('scope')}).")
            print("Next: BikeLog.exe --strava-sync")
            return 0
        client = sc.StravaClient(token_store=sc.EnvTokenStore(env_file))
        if args.strava_disconnect:
            client.deauthorize()
            res = strava.mark_disconnected(factory)
            print(f"Strava disconnected. All {res['kept_rides']} rides imported from Strava are kept.")
            return 0
        if client.tokens.load() is None:
            print("Strava is not connected yet. Run: BikeLog.exe --strava-connect", file=sys.stderr)
            return 2
        backup_database(paths, "pre-strava-sync")
        print("Importing rides from Strava (a backup was written first). This can take a few minutes...")

        def progress(page, counts):
            print(f"  page {page}: " + ", ".join(f"{k.lower()} {v}" for k, v in sorted(counts.items())), flush=True)
        res = strava.sync(factory, client, rescan=args.strava_rescan, force=True, progress=progress)
        c = res.get("counts", {})
        print("Done: " + (", ".join(f"{k.lower().replace('_', ' ')} {v}" for k, v in sorted(c.items())) or "nothing new"))
        print("Open Bike Log to see the rides. Rides without a matching bike are listed under Rides → flagged.")
        return 0
    except sc.StravaError as e:
        print(f"Strava: {e}", file=sys.stderr)
        return 1
    except sc.StravaTemporaryError as e:
        print(f"Strava: {e} Run the same command again later; it continues where it stopped.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
