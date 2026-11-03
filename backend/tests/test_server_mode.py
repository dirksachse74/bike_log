"""Server mode: Google sign-in, allowlist, CSRF, public Strava callback, backup upload/download.
Google is faked (no network); this proves our side of the flow, not Google's."""
import base64
import json
import sqlite3
import time
import urllib.parse
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from bikelog import backup
from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.server_auth import SESSION_COOKIE, ConfigError, ServerConfig, sign
from bikelog.services.reference import ensure_reference_data

PUBLIC = "https://bikelog.example.com"
ENV = {"BIKELOG_PUBLIC_URL": PUBLIC + "/", "BIKELOG_GOOGLE_CLIENT_ID": "cid.apps.googleusercontent.com",
       "BIKELOG_GOOGLE_CLIENT_SECRET": "gsecret", "BIKELOG_ALLOWED_EMAILS": "Dirk@Example.com, friend@example.com",
       "BIKELOG_SESSION_SECRET": "x" * 40}


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


class FakeGoogle:
    def __init__(self):
        self.email, self.verified, self.aud, self.nonce, self.calls = "dirk@example.com", True, ENV[
            "BIKELOG_GOOGLE_CLIENT_ID"], None, []

    def __call__(self, url, form):
        self.calls.append((url, form))
        claims = {"iss": "https://accounts.google.com", "aud": self.aud, "exp": time.time() + 300,
                  "email": self.email, "email_verified": self.verified, "nonce": self.nonce}
        return {"id_token": f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.sig", "access_token": "a"}


@pytest.fixture()
def server(engine, paths, tmp_path):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text('<meta name="bikelog-token" content="%BIKELOG_TOKEN%">', encoding="utf-8")
    cfg = ServerConfig.from_env(paths.root, ENV)
    google = FakeGoogle()
    app = create_app(factory, paths, testing=True, static_dir=static, server=cfg, google_transport=google)
    c = TestClient(app, base_url=PUBLIC)
    return c, google, cfg


def sign_in(c, google):
    start = c.get("/auth/google", follow_redirects=False)
    assert start.status_code == 303 and start.headers["location"].startswith("https://accounts.google.com/")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start.headers["location"]).query))
    assert q["redirect_uri"] == PUBLIC + "/auth/callback" and q["scope"] == "openid email"
    google.nonce = q["nonce"]
    return c.get("/auth/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)


def csrf_of(c) -> str:
    page = c.get("/").text
    return page.split('content="')[1].split('"')[0]


def test_config_from_env(paths):
    cfg = ServerConfig.from_env(paths.root, ENV)
    assert cfg.public_url == PUBLIC and cfg.host == "bikelog.example.com" and cfg.secure
    assert cfg.allowed_emails == {"dirk@example.com", "friend@example.com"}
    with pytest.raises(ConfigError, match="BIKELOG_ALLOWED_EMAILS"):
        ServerConfig.from_env(paths.root, {**ENV, "BIKELOG_ALLOWED_EMAILS": ""})
    with pytest.raises(ConfigError, match="https"):
        ServerConfig.from_env(paths.root, {**ENV, "BIKELOG_PUBLIC_URL": "http://bikelog.example.com"})
    # without a configured secret one is generated once and kept in the data directory
    a = ServerConfig.from_env(paths.root, {**ENV, "BIKELOG_SESSION_SECRET": ""})
    b = ServerConfig.from_env(paths.root, {**ENV, "BIKELOG_SESSION_SECRET": ""})
    assert a.session_secret == b.session_secret and len(a.session_secret) > 40
    assert "gsecret" not in repr(a)


def test_everything_needs_sign_in(server):
    c, _google, _cfg = server
    assert c.get("/", follow_redirects=False).headers["location"] == "/auth/login"
    assert c.get("/assets/app.js", follow_redirects=False).status_code == 303
    r = c.get("/api/bikes")
    assert r.status_code == 401 and "signed out" in r.json()["detail"]
    assert c.post("/api/backups").status_code == 401
    assert c.get("/api/health").json() == {"ok": True}          # public, but says nothing else
    assert "Sign in with Google" in c.get("/auth/login").text
    # an unknown Host header is refused (DNS rebinding, stray domains)
    assert c.get("/auth/login", headers={"host": "evil.example.net"}).status_code == 403


def test_google_sign_in_and_csrf(server):
    c, google, _cfg = server
    r = sign_in(c, google)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"]
    assert SESSION_COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    form = google.calls[0][1]
    assert form["client_secret"] == "gsecret" and form["redirect_uri"] == PUBLIC + "/auth/callback"

    assert c.get("/api/bikes").status_code == 200
    assert c.get("/api/meta").json()["server"] == {"user": "dirk@example.com"}
    assert "version" in c.get("/api/health").json()
    token = csrf_of(c)
    assert token and token != "%BIKELOG_TOKEN%"
    assert c.post("/api/backups").status_code == 403                                  # no CSRF header
    assert c.post("/api/backups", headers={"X-BikeLog-Token": "wrong"}).status_code == 403
    assert c.post("/api/backups", headers={"X-BikeLog-Token": token, "Origin": "https://evil.example.net"}).status_code == 403
    ok = c.post("/api/backups", headers={"X-BikeLog-Token": token, "Origin": PUBLIC})
    assert ok.status_code == 201
    assert ok.headers["strict-transport-security"].startswith("max-age=")

    out = c.get("/auth/logout")
    assert "Signed out" in out.text
    assert c.get("/api/bikes").status_code == 401


def test_sign_in_refusals(server):
    c, google, _cfg = server
    google.email = "stranger@example.com"
    r = sign_in(c, google)
    assert r.status_code == 403 and "stranger@example.com" in r.text
    assert c.get("/api/bikes").status_code == 401
    google.email, google.verified = "dirk@example.com", False
    assert "did not confirm" in sign_in(c, google).text
    google.verified, google.aud = True, "someone-else"
    assert "another app" in sign_in(c, google).text
    # a callback that was not started in this browser (no / wrong state) is refused
    google.aud = ENV["BIKELOG_GOOGLE_CLIENT_ID"]
    c.cookies.clear()
    assert "did not start here" in c.get("/auth/callback", params={"state": "x", "code": "y"}).text
    assert c.get("/api/bikes").status_code == 401


def test_forged_or_expired_or_removed_session(server, paths):
    c, _google, cfg = server
    c.cookies.set(SESSION_COOKIE, sign(cfg, {"e": "dirk@example.com", "s": "a", "x": time.time() + 60})[:-2] + "xx")
    assert c.get("/api/bikes").status_code == 401
    c.cookies.set(SESSION_COOKIE, sign(cfg, {"e": "dirk@example.com", "s": "a", "x": time.time() - 1}))
    assert c.get("/api/bikes").status_code == 401
    c.cookies.set(SESSION_COOKIE, sign(cfg, {"e": "dirk@example.com", "s": "a", "x": time.time() + 60}))
    assert c.get("/api/bikes").status_code == 200
    # taking an address off the allowlist locks it out at once, even with a valid cookie
    narrowed = ServerConfig.from_env(paths.root, {**ENV, "BIKELOG_ALLOWED_EMAILS": "friend@example.com"})
    assert narrowed.allowed_emails == {"friend@example.com"}
    from bikelog.server_auth import current_session

    class Req:
        cookies = {SESSION_COOKIE: sign(cfg, {"e": "dirk@example.com", "s": "a", "x": time.time() + 60})}
    assert current_session(narrowed, Req()) is None


def test_strava_uses_public_address(server):
    c, google, _cfg = server
    sign_in(c, google)
    h = {"X-BikeLog-Token": csrf_of(c)}
    st = c.get("/api/strava/status").json()
    assert st["callback_domain"] == "bikelog.example.com" and st["server"] is True
    c.put("/api/strava/credentials", json={"client_id": "12345", "client_secret": "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"},
          headers=h)
    con = c.post("/api/strava/connect", headers=h).json()
    assert con["redirect_uri"] == PUBLIC + "/api/strava/callback"
    back = c.get("/api/strava/callback", params={"state": "forged", "code": "x"}, follow_redirects=False)
    assert back.headers["location"].startswith(PUBLIC + "/#/settings?strava=error")


def test_backup_download_and_upload(server, paths):
    c, google, _cfg = server
    sign_in(c, google)
    h = {"X-BikeLog-Token": csrf_of(c)}
    name = c.post("/api/backups", headers=h).json()["name"]
    data = c.get(f"/api/backups/{name}/download").content
    assert data.startswith(b"SQLite format 3\x00")
    assert c.get("/api/backups/..%2Fdata%2Fbikelog.db/download").status_code in (400, 404)

    bad = c.post("/api/backups/upload", content=b"not a database", headers=h)
    assert bad.status_code == 400 and "not a Bike Log backup" in bad.json()["detail"]
    other = paths.root / "other.db"
    with closing(sqlite3.connect(other)) as d:
        d.execute("CREATE TABLE x (a)")
        d.commit()
    assert "not a Bike Log database" in c.post("/api/backups/upload", content=other.read_bytes(), headers=h).json()["detail"]

    up = c.post("/api/backups/upload?file_name=desktop.db", content=data, headers=h)
    assert up.status_code == 201 and up.json()["name"].endswith("-uploaded.db")
    assert up.json()["name"] in [b["name"] for b in c.get("/api/backups").json()["backups"]]
    res = c.post(f"/api/backups/{up.json()['name']}/restore", headers=h)
    assert res.status_code == 200 and res.json()["restored"] == up.json()["name"]
    assert not list(paths.backups.glob("*.part"))
    assert backup.MAX_UPLOAD_BYTES >= 100 * 1024 * 1024


def test_desktop_mode_unchanged(engine, paths):
    """No server config: still the 127.0.0.1-only app with its per-launch token, no sign-in routes."""
    factory = make_session_factory(engine)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None), base_url="http://127.0.0.1:8765")
    assert c.get("/api/bikes").status_code == 200
    assert c.get("/auth/login").status_code == 404
    assert c.get("/api/meta").json()["server"] is None
    assert c.get("/api/strava/status").json()["callback_domain"] == "localhost"
    assert c.get("/api/bikes", headers={"host": "bikelog.example.com"}).status_code == 403
