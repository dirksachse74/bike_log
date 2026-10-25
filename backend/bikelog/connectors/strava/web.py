"""Strava from the Settings page: save the API app credentials, connect via the browser, sync, disconnect.

The same files and code paths as the command-line commands: credentials and tokens live only in
<data dir>/strava.env (owner-only file), never in the database, logs or API responses (the secret is
write-only). OAuth uses a callback on this app (http://localhost:<port>/api/strava/callback, so the
Strava app's "Authorization Callback Domain" must be ``localhost``); a one-time ``state`` ties the
callback to a connect request made from this page. Syncs run in a background thread, one at a time,
after a database backup. Disconnecting keeps all rides.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from bikelog.backup import backup_database
from bikelog.connectors.strava import client as sc
from bikelog.connectors.strava import sync as strava
from bikelog.paths import DataPaths
from bikelog.services.errors import DomainError
from bikelog.timeutil import utc_now

log = logging.getLogger(__name__)
STATE_TTL_S = 15 * 60


class StravaWeb:
    def __init__(self, paths: DataPaths, factory: sessionmaker[Session], transport=sc.urllib_transport):
        self.paths = paths
        self.factory = factory
        self.transport = transport
        self.env_file: Path = paths.root / "strava.env"
        self._states: dict[str, float] = {}
        self._lock = threading.Lock()
        self.job: dict = {"running": False}
        self._thread: threading.Thread | None = None

    # -- credentials ---------------------------------------------------------
    def _env(self) -> dict:
        return sc.read_env(self.env_file)

    def credentials(self) -> dict:
        env = self._env()
        return {"client_id": env.get("STRAVA_CLIENT_ID"), "secret_saved": bool(env.get("STRAVA_CLIENT_SECRET")),
                "tokens_saved": bool(env.get("STRAVA_REFRESH_TOKEN")), "athlete_id": env.get("STRAVA_ATHLETE_ID"),
                "scope": env.get("STRAVA_SCOPE"), "env_file": str(self.env_file)}

    def save_credentials(self, client_id: str, client_secret: str | None) -> dict:
        client_id = (client_id or "").strip()
        if not client_id.isdigit():
            raise DomainError("The Client ID is the number shown on strava.com/settings/api")
        updates = {"STRAVA_CLIENT_ID": client_id}
        if client_secret and client_secret.strip():
            secret = client_secret.strip()
            if len(secret) < 20 or not secret.isalnum():
                raise DomainError("That does not look like a Strava Client Secret (40 letters and digits)")
            updates["STRAVA_CLIENT_SECRET"] = secret
        elif not self._env().get("STRAVA_CLIENT_SECRET"):
            raise DomainError("Enter the Client Secret")
        env = self._env()
        if env.get("STRAVA_CLIENT_ID") and env["STRAVA_CLIENT_ID"] != client_id:
            # tokens belong to the old API app; they cannot be used with the new one
            updates.update({k: None for k in sc.EnvTokenStore.KEYS.values()})
        self.paths.root.mkdir(parents=True, exist_ok=True)
        sc.update_env(self.env_file, updates)
        log.info("Strava app credentials saved (client id %s)", client_id)
        return self.credentials()

    def forget_credentials(self) -> dict:
        if self._env().get("STRAVA_REFRESH_TOKEN"):
            raise DomainError("Disconnect Strava first")
        sc.update_env(self.env_file, {"STRAVA_CLIENT_ID": None, "STRAVA_CLIENT_SECRET": None})
        return self.credentials()

    def client(self) -> sc.StravaClient:
        env = self._env()
        return sc.StravaClient(client_id=env.get("STRAVA_CLIENT_ID"), client_secret=env.get("STRAVA_CLIENT_SECRET"),
                               token_store=sc.EnvTokenStore(self.env_file), transport=self.transport)

    # -- OAuth ---------------------------------------------------------------
    @staticmethod
    def redirect_uri(port: int) -> str:
        return f"http://localhost:{port}/api/strava/callback"

    def start_connect(self, port: int) -> str:
        env = self._env()
        if not (env.get("STRAVA_CLIENT_ID") and env.get("STRAVA_CLIENT_SECRET")):
            raise DomainError("Save the Client ID and Client Secret first")
        state = secrets.token_urlsafe(24)
        now = time.time()
        with self._lock:
            self._states = {s: t for s, t in self._states.items() if now - t < STATE_TTL_S}
            self._states[state] = now
        return self.client().authorize_url(self.redirect_uri(port), state)

    def finish_connect(self, *, state: str | None, code: str | None, scope: str | None, error: str | None) -> dict:
        with self._lock:
            started = self._states.pop(state or "", None)
        if started is None or time.time() - started > STATE_TTL_S:
            raise DomainError("This Strava answer does not belong to a connect request from Bike Log (or it "
                              "expired). Click 'Connect with Strava' again.")
        if error or not code:
            raise DomainError("Strava access was not granted" + (f" ({error})" if error else ""))
        tok = self.client().exchange_code(code)
        tok["scope"] = tok.get("scope") or scope
        sc.EnvTokenStore(self.env_file).save(tok)
        with self.factory() as s, s.begin():
            from bikelog.models import StravaConnection
            conn = s.get(StravaConnection, strava.SOURCE_ACCOUNT)
            if conn is None:
                s.add(StravaConnection(athlete_id=strava.SOURCE_ACCOUNT, status="ACTIVE"))
            else:
                conn.status, conn.last_error = "ACTIVE", None
        private = "activity:read_all" in (tok.get("scope") or "")
        return {"athlete_id": tok["athlete_id"], "private_rides": private}

    # -- sync ----------------------------------------------------------------
    def start_sync(self, rescan: bool = False) -> dict:
        if not self._env().get("STRAVA_REFRESH_TOKEN"):
            raise DomainError("Strava is not connected yet")
        with self._lock:
            if self.job.get("running"):
                raise DomainError("A Strava sync is already running")
            self.job = {"running": True, "rescan": rescan, "started_at": utc_now(), "page": 0, "counts": {},
                        "error": None, "finished_at": None}
            self._thread = threading.Thread(target=self._run_sync, args=(rescan,), daemon=True,
                                            name="strava-sync")
            self._thread.start()
        return dict(self.job)

    def _run_sync(self, rescan: bool) -> None:
        try:
            backup_database(self.paths, "pre-strava-sync")

            def progress(page, counts):
                self.job.update(page=page, counts=dict(counts))
            res = strava.sync(self.factory, self.client(), rescan=rescan, force=True, progress=progress)
            self.job.update(counts=res.get("counts", self.job["counts"]))
        except Exception as e:  # shown on the Settings page; never contains the secret
            log.warning("Strava sync failed: %s", e)
            self.job["error"] = str(e) or type(e).__name__
        finally:
            self.job.update(running=False, finished_at=utc_now())

    def wait(self, timeout: float = 30) -> None:
        """Tests: wait for the background sync to finish."""
        if self._thread:
            self._thread.join(timeout)

    # -- disconnect ----------------------------------------------------------
    def disconnect(self) -> dict:
        if self.job.get("running"):
            raise DomainError("Wait until the sync has finished")
        self.client().deauthorize()
        return strava.mark_disconnected(self.factory)

    def status(self, session: Session) -> dict:
        return {**strava.status(session), "credentials": self.credentials(), "job": dict(self.job)}
