"""Read-only Strava REST client: OAuth, token refresh, paginated activity listing.

Standard library only. The HTTP layer is a single callable (`transport`) so tests can
replace Strava with a fake server.

Secrets: the client id/secret come from the environment or ``strava.env`` in the user's data
directory (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET); tokens are written back to that file with
owner-only permissions. Never in the database, the repo, docs or logs.

Ported from the "Build Strava ride import" thread (rides/bikelog_rides/strava_api.py); only the
location of the secrets file changed. This connector is isolated and disabled by default
(see DECISIONS.md: Strava terms unverified, no live connection possible from the build environment).
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

log = logging.getLogger("bikelog.strava")

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
DEAUTHORIZE_URL = "https://www.strava.com/oauth/deauthorize"
API_BASE = "https://www.strava.com/api/v3"
# activity:read_all = private activities too; profile:read_all = gear names.
SCOPES = "read,activity:read_all,profile:read_all"

CYCLING_SPORT_TYPES = {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide",
                       "EMountainBikeRide", "Velomobile", "Handcycle"}


class StravaError(Exception):
    """Permanent error: do not retry automatically."""


class StravaAuthError(StravaError):
    """Token invalid or revoked: the user has to connect again."""


class StravaTemporaryError(Exception):
    """Network failure, 5xx or rate limit that outlived our retries; safe to resume later."""


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None


Transport = Callable[[str, str, dict, bytes | None, float], HttpResponse]


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> HttpResponse:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return HttpResponse(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b"")


# ---------------------------------------------------------------------------
# .env file (client id/secret in, tokens out) and token storage
# ---------------------------------------------------------------------------

def find_env_file() -> Path:
    """BIKELOG_STRAVA_ENV, else strava.env in the per-user data directory (never the repo or install dir)."""
    if os.environ.get("BIKELOG_STRAVA_ENV"):
        return Path(os.environ["BIKELOG_STRAVA_ENV"])
    from bikelog.paths import default_data_dir
    return default_data_dir() / "strava.env"


def read_env(path: Path) -> dict:
    out = {}
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    return out


def update_env(path: Path, updates: dict) -> None:
    """Set/replace (value) or remove (None) keys; other lines and comments stay. Owner-only file."""
    path = Path(path)
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        lines = []
    done, out = set(), []
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip() if "=" in line else None
        if key in updates:
            done.add(key)
            if updates[key] is not None:
                out.append(f"{key}={updates[key]}")
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in done and v is not None]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:  # Windows: best effort
        pass
    os.replace(tmp, path)


class EnvTokenStore:
    """Tokens in the same .env as the client id/secret. Strava rotates refresh tokens, so every
    refresh writes the new one back here before it is used."""
    KEYS = {"athlete_id": "STRAVA_ATHLETE_ID", "refresh_token": "STRAVA_REFRESH_TOKEN",
            "access_token": "STRAVA_ACCESS_TOKEN", "expires_at": "STRAVA_TOKEN_EXPIRES_AT", "scope": "STRAVA_SCOPE"}

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else find_env_file()

    def load(self) -> dict | None:
        env = read_env(self.path)
        if not env.get("STRAVA_REFRESH_TOKEN"):
            return None
        return {"athlete_id": int(env["STRAVA_ATHLETE_ID"]) if env.get("STRAVA_ATHLETE_ID") else None,
                "refresh_token": env["STRAVA_REFRESH_TOKEN"], "access_token": env.get("STRAVA_ACCESS_TOKEN", ""),
                "expires_at": int(env.get("STRAVA_TOKEN_EXPIRES_AT") or 0), "scope": env.get("STRAVA_SCOPE")}

    def save(self, tokens: dict) -> None:
        update_env(self.path, {v: tokens.get(k) for k, v in self.KEYS.items()})

    def clear(self) -> None:
        update_env(self.path, {v: None for v in self.KEYS.values()})


class TokenStore:
    """Tokens in a JSON file readable only by the owner (used by tests and as an alternative)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return None

    def save(self, tokens: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens))
        try:
            os.chmod(tmp, 0o600)
        except OSError:  # Windows: best effort
            pass
        os.replace(tmp, self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class StravaClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 token_store: TokenStore | None = None, transport: Transport = urllib_transport,
                 timeout: float = 30.0, max_retries: int = 5, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time, max_rate_limit_wait_s: float = 16 * 60):
        env = read_env(find_env_file()) if not (client_id and client_secret) else {}
        self.client_id = client_id or os.environ.get("STRAVA_CLIENT_ID") or env.get("STRAVA_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("STRAVA_CLIENT_SECRET") or env.get("STRAVA_CLIENT_SECRET")
        self.tokens = token_store or EnvTokenStore()
        self.transport = transport
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep
        self.clock = clock
        self.max_rate_limit_wait_s = max_rate_limit_wait_s
        self.last_rate_usage: str | None = None
        self.last_headers: dict = {}

    # -- OAuth -------------------------------------------------------------
    def authorize_url(self, redirect_uri: str, state: str) -> str:
        self._require_app()
        q = {"client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
             "approval_prompt": "auto", "scope": SCOPES, "state": state}
        return AUTHORIZE_URL + "?" + urllib.parse.urlencode(q)

    def exchange_code(self, code: str) -> dict:
        """Authorization code -> tokens. Returns the token record incl. athlete id and granted scope."""
        self._require_app()
        data = self._token_request({"grant_type": "authorization_code", "code": code})
        tok = {"athlete_id": data["athlete"]["id"], "access_token": data["access_token"],
               "refresh_token": data["refresh_token"], "expires_at": data["expires_at"],
               "scope": data.get("scope")}
        self.tokens.save(tok)
        return tok

    def authorize_via_localhost(self, port: int = 8765, open_browser: bool = True, timeout_s: int = 300) -> dict:
        """One-time OAuth: open the authorize URL, catch ?code= on http://localhost:PORT, exchange it."""
        import secrets
        from http.server import BaseHTTPRequestHandler, HTTPServer
        state = secrets.token_urlsafe(16)
        result = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" not in q and "error" not in q:  # favicon etc.
                    self.send_response(404)
                    self.end_headers()
                    return
                ok = q.get("state", [""])[0] == state and "code" in q
                result.update(code=q.get("code", [None])[0] if ok else None, scope=q.get("scope", [""])[0],
                              error=q.get("error", [None])[0] or (None if ok else "state mismatch"))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Bike Log: Strava connected. You can close this tab." if ok
                                 else b"Bike Log: Strava authorisation failed. Check the terminal.")

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", port), Handler)
        srv.timeout = timeout_s
        url = self.authorize_url(f"http://localhost:{port}", state)
        print(f"Opening Strava to authorise Bike Log. If no browser opens, visit:\n{url}\n")
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        deadline = time.time() + timeout_s
        while not result and time.time() < deadline:
            srv.handle_request()
        srv.server_close()
        if not result.get("code"):
            raise StravaError(f"Strava authorisation not completed: {result.get('error') or 'timeout'}")
        if "activity:read_all" not in (result.get("scope") or ""):
            log.warning("activity:read_all was not granted: private rides will not be imported")
        tok = self.exchange_code(result["code"])
        tok["scope"] = tok.get("scope") or result.get("scope")
        self.tokens.save(tok)
        return tok

    def athlete_id(self) -> int | None:
        tok = self.tokens.load()
        return tok["athlete_id"] if tok else None

    def deauthorize(self) -> None:
        """Revoke this app's access at Strava, then forget the local tokens."""
        tok = self.tokens.load()
        if tok:
            try:
                body = urllib.parse.urlencode({"access_token": self._access_token()}).encode()
                self.transport("POST", DEAUTHORIZE_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                               body, self.timeout)
            except Exception as e:  # revoke is best effort; local tokens are removed regardless
                log.warning("deauthorize failed: %s", e)
        self.tokens.clear()

    def _require_app(self):
        if not (self.client_id and self.client_secret):
            raise StravaError("STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET missing: put them in strava.env in the data directory (see docs/strava.md).")

    def _token_request(self, fields: dict) -> dict:
        body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                       **fields}).encode()
        r = self._send("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if r.status in (400, 401):
            raise StravaAuthError(f"Strava rejected the token request ({r.status}); connect Strava again.")
        if r.status != 200:
            raise StravaError(f"token request failed: HTTP {r.status}")
        return r.json()

    def _access_token(self) -> str:
        tok = self.tokens.load()
        if not tok:
            raise StravaAuthError("Strava is not connected.")
        if tok["expires_at"] - 300 <= self.clock():  # refresh 5 min early
            self._require_app()
            data = self._token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
            tok.update(access_token=data["access_token"], refresh_token=data["refresh_token"],
                       expires_at=data["expires_at"])
            self.tokens.save(tok)  # Strava may rotate the refresh token: persist before use
            log.info("refreshed Strava access token")
        return tok["access_token"]

    # -- HTTP with retries ---------------------------------------------------
    def _send(self, method, url, headers, body=None) -> HttpResponse:
        attempt = 0
        while True:
            try:
                r = self.transport(method, url, headers, body, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                r, err = None, e
            if r is not None:
                self.last_headers = r.headers
                self.last_rate_usage = r.headers.get("x-ratelimit-usage", self.last_rate_usage)
                if r.status == 429:
                    wait = self._rate_limit_wait()
                    if wait > self.max_rate_limit_wait_s:
                        raise StravaTemporaryError("Strava daily rate limit reached; sync resumes later.")
                    log.warning("Strava rate limit hit (usage %s); waiting %.0f s", self.last_rate_usage, wait)
                    self.sleep(wait)
                    continue  # rate-limit waits do not count as failed attempts
                if r.status < 500:
                    return r
                err = StravaError(f"HTTP {r.status}")
            attempt += 1
            if attempt > self.max_retries:
                raise StravaTemporaryError(f"Strava unavailable after {self.max_retries} retries: {err}")
            delay = min(60.0, 2 ** attempt) + random.uniform(0, 1)
            log.warning("Strava request failed (%s); retry %d in %.1f s", err, attempt, delay)
            self.sleep(delay)

    def _rate_limit_wait(self) -> float:
        """Seconds to the next 15-minute window, or a full day if the daily quota is used up.
        Strava reports 'short,daily' pairs in X-RateLimit-Limit / X-RateLimit-Usage (and X-ReadRateLimit-*)."""
        def pair(name):
            try:
                a, b = (self.last_headers.get(name) or "").split(",")
                return int(a), int(b)
            except ValueError:
                return None
        for kind in ("x-readratelimit", "x-ratelimit"):
            lim, use = pair(f"{kind}-limit"), pair(f"{kind}-usage")
            if lim and use and use[1] >= lim[1]:
                return 24 * 3600
        return 900 - (self.clock() % 900) + 5

    def get(self, path: str, params: dict | None = None):
        url = API_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        r = self._send("GET", url, {"Authorization": f"Bearer {self._access_token()}"})
        if r.status == 401:
            raise StravaAuthError("Strava access was revoked or expired; connect Strava again.")
        if r.status == 404:
            return None
        if r.status != 200:
            raise StravaError(f"GET {path} failed: HTTP {r.status} {r.body[:200]!r}")
        return r.json()

    # -- Read endpoints -----------------------------------------------------
    def iter_activity_pages(self, after_epoch: int, per_page: int = 100, start_page: int = 1
                            ) -> Iterator[tuple[int, list[dict]]]:
        """Pages of SummaryActivity started after `after_epoch`, oldest first; stops on an empty page."""
        page = start_page
        while True:
            items = self.get("/athlete/activities", {"after": after_epoch, "page": page, "per_page": per_page}) or []
            if not items:
                return
            yield page, items
            page += 1

    def get_gear(self, gear_id: str) -> dict | None:
        return self.get(f"/gear/{gear_id}")
