"""Application settings stored in the database (app_setting)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from bikelog.models import AppSetting
from bikelog.services.errors import DomainError

DEFAULTS = {
    "timezone": "Europe/Berlin",
    "import_start_date": "",          # inclusive local date; empty = no lower bound
    "trainer_profile_for_virtual": "DIRECT_DRIVE_TRAINER",
    "duplicate_window_km_pct": "5",
    "demo_mode": "0",                 # set only in databases created by the demo launcher
}

EDITABLE = {"timezone", "import_start_date", "trainer_profile_for_virtual"}


def get(session: Session, key: str) -> str:
    row = session.get(AppSetting, key)
    return row.value if row else DEFAULTS[key]


def tz(session: Session) -> str:
    return get(session, "timezone")


def set_value(session: Session, key: str, value: str, *, internal: bool = False) -> None:
    if not internal and key not in EDITABLE:
        raise DomainError(f"Setting {key} cannot be changed")
    if key == "timezone":
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except Exception as e:  # noqa: BLE001
            raise DomainError(f"Unknown timezone {value!r}") from e
    if key == "import_start_date" and value:
        from datetime import date
        try:
            date.fromisoformat(value)
        except ValueError as e:
            raise DomainError("Import start date must be YYYY-MM-DD") from e
    row = session.get(AppSetting, key)
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=key, value=value))
    session.flush()


def all_settings(session: Session) -> dict:
    out = dict(DEFAULTS)
    for row in session.query(AppSetting).all():
        out[row.key] = row.value
    return out
