"""Local-only protection: Host check (DNS rebinding), per-launch token on every mutation (CSRF), no CORS."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str, allow_test_host: bool = False):
        super().__init__(app)
        self.token = token
        self.allow_test_host = allow_test_host

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS and not (self.allow_test_host and host == "testserver"):
            return JSONResponse({"detail": "Bike Log only answers on 127.0.0.1"}, status_code=403)
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            if request.headers.get("x-bikelog-token") != self.token:
                return JSONResponse({"detail": "Missing or wrong X-BikeLog-Token; reload the page."}, status_code=403)
        return await call_next(request)
