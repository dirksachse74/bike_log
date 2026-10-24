"""In-memory stand-in for the Strava API, plugged in as StravaClient.transport."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from bikelog.connectors.strava.client import HttpResponse, StravaClient, TokenStore

ATHLETE = 43217313


def act(i: int, start: str, km: float = 40.0, sport: str = "Ride", gear: str | None = "b90000001", **kw) -> dict:
    a = {"id": 10_000_000 + i, "athlete": {"id": ATHLETE}, "name": f"Ride {i}", "start_date": start,
         "start_date_local": start.replace("Z", ""), "timezone": "(GMT+01:00) Europe/Berlin",
         "distance": km * 1000, "moving_time": int(km * 120), "elapsed_time": int(km * 140),
         "sport_type": sport, "type": sport, "gear_id": gear, "trainer": False, "manual": False,
         "commute": False, "private": False,
         # fields we must ignore:
         "map": {"summary_polyline": "abc"}, "average_watts": 200, "average_heartrate": 140}
    a.update(kw)
    return a


class FakeStrava:
    def __init__(self, activities=None, gear=None):
        self.activities = {a["id"]: a for a in (activities or [])}
        self.gear = gear or {}
        self.calls = []
        self.fail_plan = {}          # call number -> 'net' | 500 | 429
        self.deleted_404 = set()      # ids that GET /activities/{id} reports as 404
        self.token_counter = 0
        self.now = 1_800_000_000      # fake clock for token expiry

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url))
        n = len(self.calls)
        f = self.fail_plan.pop(n, None)
        if f == "net":
            raise ConnectionError("simulated network failure")
        if f in (500, 503):
            return HttpResponse(f, {}, b"")
        if f == 429:
            return HttpResponse(429, {"x-ratelimit-usage": "200,500"}, b"")
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/oauth/token":
            form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
            self.token_counter += 1
            data = {"access_token": f"at{self.token_counter}", "refresh_token": f"rt{self.token_counter}",
                    "expires_at": self.now + 6 * 3600, "athlete": {"id": ATHLETE}, "scope": "read,activity:read_all"}
            if form.get("grant_type") == "refresh_token" and not form.get("refresh_token", "").startswith("rt"):
                return HttpResponse(400, {}, b"{}")
            return self._json(data)
        if u.path == "/oauth/deauthorize":
            return self._json({})
        if u.path == "/api/v3/athlete/activities":
            after = int(q.get("after", 0))
            per = int(q.get("per_page", 30))
            page = int(q.get("page", 1))
            items = sorted((a for a in self.activities.values() if self._epoch(a["start_date"]) > after),
                           key=lambda a: a["start_date"])
            return self._json(items[(page - 1) * per: page * per])
        if u.path.startswith("/api/v3/activities/"):
            aid = int(u.path.rsplit("/", 1)[1])
            if aid in self.deleted_404 or aid not in self.activities:
                return HttpResponse(404, {}, b'{"message":"Record Not Found"}')
            return self._json(self.activities[aid])
        if u.path.startswith("/api/v3/gear/"):
            gid = u.path.rsplit("/", 1)[1]
            return self._json(self.gear[gid]) if gid in self.gear else HttpResponse(404, {}, b"")
        return HttpResponse(404, {}, b"")

    @staticmethod
    def _epoch(iso):
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())

    @staticmethod
    def _json(obj):
        return HttpResponse(200, {"x-ratelimit-usage": "10,100"}, json.dumps(obj).encode())

    def list_calls(self):
        return [c for c in self.calls if "/athlete/activities" in c[1]]


def client_for(fake: FakeStrava, token_dir) -> StravaClient:
    store = TokenStore(token_dir / "tokens.json")
    store.save({"athlete_id": ATHLETE, "access_token": "at0", "refresh_token": "rt0",
                "expires_at": fake.now + 3600, "scope": "read,activity:read_all"})
    return StravaClient("cid", "secret", store, transport=fake, sleep=lambda s: None, clock=lambda: fake.now,
                        max_retries=3)
