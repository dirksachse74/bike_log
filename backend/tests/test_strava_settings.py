"""Strava from the Settings page (no command line), against the in-memory fake Strava.
Like the other Strava tests this does NOT prove the real Strava works."""
import urllib.parse

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bikelog.api.app import create_app
from bikelog.connectors.strava import client as sc
from bikelog.db import make_session_factory, session_scope
from bikelog.models import Ride
from bikelog.services import inventory as inv
from bikelog.services import settings
from bikelog.services.reference import ensure_reference_data

from fake_strava import FakeStrava, act

SECRET = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"


def app_with(engine, paths, fake):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
        inv.create_bike(s, name="BMC Roadmachine", strava_gear_id="90000001")
        settings.set_value(s, "import_start_date", "2026-10-01")
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None, strava_transport=fake),
                   base_url="http://127.0.0.1:8765")
    c.headers.update({"X-BikeLog-Token": "t"})
    return c, factory


def test_connect_sync_disconnect_from_settings(engine, paths):
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z", 50, gear="b90000001"), act(2, "2026-10-03T08:00:00Z", 30)])
    c, factory = app_with(engine, paths, fake)
    st = c.get("/api/strava/status").json()
    assert st["credentials"]["secret_saved"] is False and st["connected"] is False
    assert c.post("/api/strava/connect").status_code == 400                     # credentials first
    assert c.put("/api/strava/credentials", json={"client_id": "abc", "client_secret": SECRET}).status_code == 400
    r = c.put("/api/strava/credentials", json={"client_id": "12345", "client_secret": SECRET}).json()
    assert r["client_id"] == "12345" and r["secret_saved"] is True
    assert SECRET not in c.get("/api/strava/status").text                      # secret is write-only
    assert sc.read_env(paths.root / "strava.env")["STRAVA_CLIENT_SECRET"] == SECRET

    con = c.post("/api/strava/connect").json()
    assert con["redirect_uri"] == "http://localhost:8765/api/strava/callback"
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(con["authorize_url"]).query))
    assert q["client_id"] == "12345" and q["redirect_uri"] == con["redirect_uri"]
    # a callback with a forged state is refused
    bad = c.get("/api/strava/callback", params={"state": "forged", "code": "x"}, follow_redirects=False)
    assert bad.status_code == 303 and "strava=error" in bad.headers["location"]
    ok = c.get("/api/strava/callback", params={"state": q["state"], "code": "c0de", "scope": "read,activity:read_all"},
               headers={"host": "localhost:8765"}, follow_redirects=False)
    assert ok.headers["location"].startswith("http://127.0.0.1:8765/#/settings?strava=connected")
    assert c.get("/api/strava/status").json()["connected"] is True
    # the state is single-use
    again = c.get("/api/strava/callback", params={"state": q["state"], "code": "c0de"}, follow_redirects=False)
    assert "strava=error" in again.headers["location"]

    assert c.post("/api/strava/sync", json={}).json()["running"] is True
    c.app.state.strava.wait()
    st = c.get("/api/strava/status").json()
    assert st["job"]["running"] is False and st["job"]["error"] is None
    assert st["live_connection_verified"] is True        # a sync succeeded (here against the fake)
    with factory() as s:
        assert s.scalar(select(func.count(Ride.id))) == 2
    assert any(p.name.startswith("bikelog-") and "pre-strava-sync" in p.name for p in paths.backups.iterdir())

    d = c.post("/api/strava/disconnect").json()
    assert d["kept_rides"] == 2
    with factory() as s:
        assert s.scalar(select(func.count(Ride.id))) == 2               # disconnect deletes nothing
    assert c.get("/api/strava/status").json()["credentials"]["tokens_saved"] is False
    assert c.delete("/api/strava/credentials").json()["client_id"] is None


def test_sync_errors_are_shown_not_raised(engine, paths):
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z")])
    c, _ = app_with(engine, paths, fake)
    c.put("/api/strava/credentials", json={"client_id": "1", "client_secret": SECRET})
    sc.EnvTokenStore(paths.root / "strava.env").save({"athlete_id": 1, "access_token": "x", "refresh_token": "bad",
                                                     "expires_at": 0, "scope": "read"})
    c.post("/api/strava/sync", json={})
    c.app.state.strava.wait()
    job = c.get("/api/strava/status").json()["job"]
    assert job["running"] is False and "connect Strava again" in job["error"]
