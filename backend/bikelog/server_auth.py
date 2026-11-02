"""Server mode: Bike Log on a rented server, reachable over HTTPS, with Google sign-in.

Only the Google accounts listed in BIKELOG_ALLOWED_EMAILS get in (single user, maybe a few). The desktop
app does not use this module at all; it keeps the 127.0.0.1 + per-launch token protection in api/security.py.

How a sign-in works (OpenID Connect authorization code flow, no extra libraries):
  /auth/login        small page with a "Sign in with Google" button
  /auth/google       sets a short-lived signed cookie with a random state + nonce, redirects to Google
  /auth/callback     checks the state, swaps the code for tokens at Google's token endpoint (server to server,
                     over TLS, with the client secret), checks the ID token claims (issuer, audience, expiry,
                     nonce, verified e-mail on the allowlist), then sets the session cookie
  /auth/logout       deletes the session cookie

The ID token comes straight from Google's token endpoint over TLS, so its signature does not need to be
checked again (OpenID Connect Core 1.0, section 3.1.3.7, point 6).

Session cookie: HMAC-SHA256 signed JSON {email, session id, expiry}; HttpOnly, Secure, SameSite=Lax.
The allowlist is checked again on every request, so removing an address locks it out at once.
Mutations additionally need the X-BikeLog-Token header (CSRF), which is derived from the session id.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

log = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

SESSION_COOKIE = "bikelog_session"
LOGIN_COOKIE = "bikelog_login"
LOGIN_TTL_S = 10 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# reachable without signing in: the sign-in pages themselves and the health check used by Docker
PUBLIC_PATHS = ("/auth/", "/api/health")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}   # Docker's health check talks to the container directly


class ConfigError(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class ServerConfig:
    public_url: str                     # e.g. https://bikelog.example.com (no trailing slash)
    google_client_id: str
    google_client_secret: str = field(repr=False)
    allowed_emails: frozenset[str]
    session_secret: bytes = field(repr=False)
    session_days: int = 30

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.public_url).hostname or ""

    @property
    def secure(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def callback_url(self) -> str:
        return self.public_url + "/auth/callback"

    @classmethod
    def from_env(cls, data_root: Path, env: dict[str, str] | None = None) -> "ServerConfig":
        env = dict(os.environ if env is None else env)
        missing = [k for k in ("BIKELOG_PUBLIC_URL", "BIKELOG_GOOGLE_CLIENT_ID", "BIKELOG_GOOGLE_CLIENT_SECRET",
                               "BIKELOG_ALLOWED_EMAILS") if not (env.get(k) or "").strip()]
        if missing:
            raise ConfigError("Server mode needs these settings (see deploy/README.md): " + ", ".join(missing))
        public = env["BIKELOG_PUBLIC_URL"].strip().rstrip("/")
        parts = urllib.parse.urlsplit(public)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.path not in ("", "/"):
            raise ConfigError("BIKELOG_PUBLIC_URL must look like https://bikelog.example.com")
        if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS:
            raise ConfigError("BIKELOG_PUBLIC_URL must start with https:// (Google sign-in needs HTTPS)")
        emails = frozenset(e.strip().lower() for e in env["BIKELOG_ALLOWED_EMAILS"].replace(";", ",").split(",")
                           if e.strip())
        if not emails or any("@" not in e for e in emails):
            raise ConfigError("BIKELOG_ALLOWED_EMAILS must be one or more e-mail addresses, separated by commas")
        secret = (env.get("BIKELOG_SESSION_SECRET") or "").strip().encode() or _stored_secret(data_root)
        days = int(env.get("BIKELOG_SESSION_DAYS") or 30)
        return cls(public_url=public, google_client_id=env["BIKELOG_GOOGLE_CLIENT_ID"].strip(),
                   google_client_secret=env["BIKELOG_GOOGLE_CLIENT_SECRET"].strip(), allowed_emails=emails,
                   session_secret=secret, session_days=max(1, days))


def _stored_secret(root: Path) -> bytes:
    """A random signing key kept in the data directory. Deleting the file signs everybody out."""
    f = root / "session.key"
    if not f.exists():
        root.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass
    return f.read_text(encoding="utf-8").strip().encode()


# ---------------------------------------------------------------- signed values

def sign(cfg: ServerConfig, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(cfg.session_secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def unsign(cfg: ServerConfig, value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    body, sig = value.rsplit(".", 1)
    want = _b64(hmac.new(cfg.session_secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    try:
        data = json.loads(_unb64(body))
    except ValueError:
        return None
    if not isinstance(data, dict) or float(data.get("x", 0)) < time.time():
        return None
    return data


def csrf_token(cfg: ServerConfig, session: dict) -> str:
    return _b64(hmac.new(cfg.session_secret, f"csrf:{session['s']}".encode(), hashlib.sha256).digest())


def current_session(cfg: ServerConfig, request: Request) -> dict | None:
    data = unsign(cfg, request.cookies.get(SESSION_COOKIE))
    if data and str(data.get("e", "")).lower() in cfg.allowed_emails:
        return data
    return None


# ---------------------------------------------------------------- Google

Transport = Callable[[str, dict], dict]


def urllib_transport(url: str, form: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error_description") or ""
        except ValueError:
            detail = ""
        raise AuthError(f"Google refused the sign-in ({e.code}{': ' + detail if detail else ''})") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise AuthError(f"Could not reach Google ({e})") from None


class AuthError(Exception):
    pass


def authorize_url(cfg: ServerConfig, state: str, nonce: str) -> str:
    q = {"client_id": cfg.google_client_id, "redirect_uri": cfg.callback_url, "response_type": "code",
         "scope": "openid email", "state": state, "nonce": nonce, "prompt": "select_account"}
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(q)


def check_id_token(cfg: ServerConfig, id_token: str, nonce: str) -> str:
    """Return the verified, allowed e-mail address or raise AuthError."""
    try:
        claims = json.loads(_unb64(id_token.split(".")[1]))
    except (IndexError, ValueError):
        raise AuthError("Google sent an unreadable answer") from None
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("The answer did not come from Google")
    aud = claims.get("aud")
    if aud != cfg.google_client_id and not (isinstance(aud, list) and cfg.google_client_id in aud):
        raise AuthError("The answer was meant for another app")
    if float(claims.get("exp", 0)) < time.time() - 60:
        raise AuthError("The sign-in expired; try again")
    if not nonce or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise AuthError("The sign-in does not belong to this browser; try again")
    email = str(claims.get("email", "")).lower()
    if not email or claims.get("email_verified") not in (True, "true"):
        raise AuthError("Google did not confirm an e-mail address for this account")
    if email not in cfg.allowed_emails:
        raise NotAllowed(email)
    return email


class NotAllowed(AuthError):
    def __init__(self, email: str):
        super().__init__(email)
        self.email = email


# ---------------------------------------------------------------- pages

def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} · Bike Log</title>
<style>body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#fff;color:#242428;
margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px}}
main{{max-width:380px;width:100%;text-align:center}}h1{{font-size:1.4rem;margin:0 0 .5rem}}
p{{color:#6d6d78;line-height:1.5}}a.btn{{display:inline-block;margin-top:1rem;padding:.7rem 1.2rem;border-radius:6px;
background:#f4511e;color:#fff;text-decoration:none;font-weight:600}}.logo{{color:#f4511e;font-weight:800;
letter-spacing:.02em;margin-bottom:1.5rem}}</style></head><body><main><div class="logo">BIKE LOG</div>
{body}</main></body></html>""", status_code=status, headers={"Cache-Control": "no-store"})


def login_page(message: str = "") -> HTMLResponse:
    extra = f"<p>{html.escape(message)}</p>" if message else ""
    return _page("Sign in", f"<h1>Sign in</h1>{extra}<p>Use your Google account.</p>"
                            '<a class="btn" href="/auth/google">Sign in with Google</a>')


def add_auth_routes(app, cfg: ServerConfig, transport: Transport | None = None) -> None:
    send = transport or urllib_transport
    max_age = cfg.session_days * 86400

    def cookie(resp: Response, name: str, value: str, age: int) -> None:
        resp.set_cookie(name, value, max_age=age, httponly=True, secure=cfg.secure, samesite="lax", path="/")

    @app.get("/auth/login", include_in_schema=False)
    def auth_login(request: Request):
        if current_session(cfg, request):
            return RedirectResponse("/", status_code=303)
        return login_page()

    @app.get("/auth/google", include_in_schema=False)
    def auth_google():
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        resp = RedirectResponse(authorize_url(cfg, state, nonce), status_code=303)
        cookie(resp, LOGIN_COOKIE, sign(cfg, {"st": state, "n": nonce, "x": time.time() + LOGIN_TTL_S}), LOGIN_TTL_S)
        return resp

    @app.get("/auth/callback", include_in_schema=False)
    def auth_callback(request: Request, state: str | None = None, code: str | None = None,
                      error: str | None = None):
        pending = unsign(cfg, request.cookies.get(LOGIN_COOKIE))
        if not pending or not state or not hmac.compare_digest(str(pending.get("st", "")), state):
            return login_page("That sign-in did not start here or took too long. Please try again.")
        if error or not code:
            return login_page("Google sign-in was cancelled.")
        try:
            tokens = send(GOOGLE_TOKEN_URL, {"code": code, "client_id": cfg.google_client_id,
                                             "client_secret": cfg.google_client_secret,
                                             "redirect_uri": cfg.callback_url, "grant_type": "authorization_code"})
            email = check_id_token(cfg, str(tokens.get("id_token") or ""), str(pending.get("n", "")))
        except NotAllowed as e:
            log.warning("sign-in refused for %s (not on BIKELOG_ALLOWED_EMAILS)", e.email)
            resp = _page("Not allowed", f"<h1>Not allowed</h1><p>The Google account <strong>{html.escape(e.email)}"
                                        "</strong> may not use this Bike Log.</p>"
                                        '<a class="btn" href="/auth/google">Use another account</a>', 403)
            resp.delete_cookie(LOGIN_COOKIE, path="/")
            return resp
        except AuthError as e:
            log.warning("sign-in failed: %s", e)
            return login_page(str(e))
        log.info("signed in: %s", email)
        resp = RedirectResponse("/", status_code=303)
        cookie(resp, SESSION_COOKIE, sign(cfg, {"e": email, "s": secrets.token_urlsafe(16),
                                                "x": time.time() + max_age}), max_age)
        resp.delete_cookie(LOGIN_COOKIE, path="/")
        return resp

    @app.get("/auth/logout", include_in_schema=False)
    def auth_logout():
        resp = _page("Signed out", "<h1>Signed out</h1><p>See you after the next ride.</p>"
                                   '<a class="btn" href="/auth/login">Sign in again</a>')
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp


# ---------------------------------------------------------------- middleware

class ServerSecurityMiddleware(BaseHTTPMiddleware):
    """Every request needs a valid session except the sign-in pages and the health check.
    Mutations also need the CSRF header and, if the browser sends one, a matching Origin."""

    def __init__(self, app, cfg: ServerConfig, allow_test_host: bool = False):
        super().__init__(app)
        self.cfg = cfg
        self.origin = cfg.public_url
        self.hosts = {cfg.host, *LOCAL_HOSTS} | ({"testserver"} if allow_test_host else set())

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in self.hosts:
            return JSONResponse({"detail": "Unknown host"}, status_code=403)
        path = request.url.path
        session = current_session(self.cfg, request)
        if session is not None:
            request.state.user = session["e"]
        if not path.startswith(PUBLIC_PATHS):
            if session is None:
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "You are signed out. Reload the page to sign in again."},
                                        status_code=401)
                return RedirectResponse("/auth/login", status_code=303)
            request.state.csrf = csrf_token(self.cfg, session)
            if request.method not in SAFE_METHODS and path.startswith("/api/"):
                origin = request.headers.get("origin")
                if origin and origin.rstrip("/") != self.origin:
                    return JSONResponse({"detail": "Request from another site refused"}, status_code=403)
                if not hmac.compare_digest(request.headers.get("x-bikelog-token") or "", request.state.csrf):
                    return JSONResponse({"detail": "Missing or wrong X-BikeLog-Token; reload the page."},
                                        status_code=403)
        resp = await call_next(request)
        if self.cfg.secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp
