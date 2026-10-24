"""Time handling.

Two kinds of values are accepted everywhere a point in time is entered:

* date-only ``YYYY-MM-DD``: no clock time is invented. For ordering it means the start of that
  local day (installation and service periods are start-inclusive, end-exclusive).
* a full datetime (ISO 8601). Naive values are local time in the user's timezone.

Stored instants are UTC strings ``YYYY-MM-DDTHH:MM:SSZ`` so string comparison equals time comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

FAR_FUTURE = "9999-12-31T00:00:00Z"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_str(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


@dataclass(frozen=True)
class When:
    """A parsed point in time as entered by the user."""
    raw: str               # normalised: 'YYYY-MM-DD' or UTC 'YYYY-MM-DDTHH:MM:SSZ'
    utc: str               # instant used for ordering
    local_date: str        # local calendar date
    date_only: bool


def parse_when(value: str | date | datetime, tz: str) -> When:
    zone = ZoneInfo(tz)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=zone)
        u = to_utc_str(dt)
        return When(u, u, dt.astimezone(zone).date().isoformat(), False)
    if isinstance(value, date):
        value = value.isoformat()
    s = str(value).strip()
    if len(s) == 10:
        d = date.fromisoformat(s)
        start = datetime(d.year, d.month, d.day, tzinfo=zone)
        return When(s, to_utc_str(start), s, True)
    s2 = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError as e:
        raise ValueError(f"Not a date or datetime: {value!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    u = to_utc_str(dt)
    return When(u, u, dt.astimezone(zone).date().isoformat(), False)


def local_date_of(utc: str, tz: str) -> str:
    return parse_utc(utc).astimezone(ZoneInfo(tz)).date().isoformat()


def today_local(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def days_between(a: date, b: date) -> int:
    return (b - a).days


def next_day(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()
