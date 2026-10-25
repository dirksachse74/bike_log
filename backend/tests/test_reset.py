"""Settings → Fresh start: back up (kept), empty database, Strava kept or cleared; restore any backup.
Runs against the real app and a real SQLite file while the app is 'running' (TestClient)."""
import urllib.parse

import pytest
from sqlalchemy import func, select

from bikelog import backup, reset
from bikelog.connectors.strava import client as sc
from bikelog.models import Bike, Ride, ServiceRule
from bikelog.services.errors import DomainError

from fake_strava import FakeStrava, act
from test_strava_settings import SECRET, app_with


def connect(c):
    c.put("/api/strava/credentials", json={"client_id": "12345", "client_secret": SECRET})
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(c.post("/api/strava/connect").json()["authorize_url"]).query))
    c.get("/api/strava/callback", params={"state": q["state"], "code": "c0de", "scope": "read,activity:read_all"},
          headers={"host": "localhost:8765"}, follow_redirects=False)
    c.post("/api/strava/sync", json={})
    c.app.state.strava.wait()


def count(factory, model):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_fresh_start_keeps_a_backup_and_strava_and_can_be_undone(engine, paths):
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z", 50, gear="b90000001"), act(2, "2026-10-03T08:00:00Z", 30)])
    c, factory = app_with(engine, paths, fake)
    connect(c)
    assert count(factory, Ride) == 2 and count(factory, Bike) == 1

    r = c.post("/api/admin/reset", json={"confirm": "reset please"})
    assert r.status_code == 400 and "Type RESET" in r.json()["detail"]
    assert count(factory, Bike) == 1                                       # nothing happened

    r = c.post("/api/admin/reset", json={"confirm": "RESET"}).json()
    assert count(factory, Bike) == 0 and count(factory, Ride) == 0
    assert count(factory, ServiceRule) > 0                                  # default rules are back
    assert c.get("/api/health").json()["schema"]
    assert r["strava"] == "kept (connected)"
    kept = paths.backups / r["backup"]
    assert kept.exists() and backup.KEPT_MARK in kept.name and r["backup_path"] == str(kept)
    listed = {b["name"]: b for b in c.get("/api/backups").json()["backups"]}
    assert listed[kept.name]["kept"] is True
    # the empty database works normally, and Strava fills it again without connecting again
    assert c.get("/api/strava/status").json()["connected"] is True
    c.post("/api/strava/sync", json={})
    c.app.state.strava.wait()
    assert count(factory, Ride) == 2
    assert c.post("/api/bikes", json={"name": "TIME NXR"}).status_code == 201

    # the kept backup survives the automatic pruning of old backups
    for i in range(backup.KEEP_AUTO_BACKUPS + 2):
        (paths.backups / f"bikelog-2026010{i % 10}T00000{i % 10}Z-x{i:02d}.db").write_bytes(b"")
    backup.prune_backups(paths)
    assert kept.exists()

    # undo: restore the backup taken before the fresh start
    res = c.post(f"/api/backups/{kept.name}/restore").json()
    assert res["restored"] == kept.name and backup.KEPT_MARK in res["backup"]
    with factory() as s:
        assert [b.name for b in s.scalars(select(Bike))] == ["BMC Roadmachine"]
    assert count(factory, Ride) == 2
    assert c.post("/api/bikes", json={"name": "Cube SL Road SL"}).status_code == 201   # writable after restore


def test_fresh_start_can_clear_strava_and_refuses_bad_backups(engine, paths):
    fake = FakeStrava([act(1, "2026-10-02T08:00:00Z", 50)])
    c, factory = app_with(engine, paths, fake)
    connect(c)
    r = c.post("/api/admin/reset", json={"confirm": "RESET", "clear_strava": True}).json()
    assert r["strava"] == "cleared"
    env = sc.read_env(paths.root / "strava.env")
    assert not any(v for k, v in env.items() if k.startswith("STRAVA_"))
    st = c.get("/api/strava/status").json()
    assert st["connected"] is False and st["credentials"]["client_id"] is None

    with pytest.raises(DomainError, match="No such backup"):
        reset._backup_file(paths, "../strava.env")                  # only files inside backups/
    assert c.post("/api/backups/nope.db/restore").status_code == 400
    (paths.backups / "bikelog-junk.db").write_bytes(b"not a database")
    assert c.post("/api/backups/bikelog-junk.db/restore").status_code == 400
