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
    "sample_data": "0",               # "1" = made-up sample data added on first start (until Fresh start)
    "default_tire_setup": "TUBE",     # used by reminders for wheels whose tube/tubeless is not set
    "spare_minimums": '{"INNER_TUBE": 2, "TIRE": 1}',   # spares to keep per part type (JSON); 0 = no check
    "spoke_relace_after": "3",        # broken spokes on one wheel before re-lacing it with new spokes
}

EDITABLE = {"timezone", "import_start_date", "trainer_profile_for_virtual", "default_tire_setup", "spare_minimums",
            "spoke_relace_after"}


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
    if key == "default_tire_setup":
        from bikelog.catalog import TIRE_SETUPS
        if value not in TIRE_SETUPS:
            raise DomainError(f"Default tire setup must be one of {', '.join(TIRE_SETUPS)}")
    if key == "spoke_relace_after" and not (value.isdigit() and 1 <= int(value) <= 20):
        raise DomainError("Re-lace after: a whole number of broken spokes from 1 to 20")
    if key == "spare_minimums":
        value = _spare_minimums_json(value)
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


def _spare_minimums_json(value: str) -> str:
    import json

    from bikelog.catalog import COMPONENT_TYPES
    try:
        data = json.loads(value or "{}")
    except ValueError as e:
        raise DomainError("Spare minimums must be JSON like {\"INNER_TUBE\": 2}") from e
    if not isinstance(data, dict):
        raise DomainError("Spare minimums must be JSON like {\"INNER_TUBE\": 2}")
    out = {}
    for k, v in data.items():
        if k not in COMPONENT_TYPES:
            raise DomainError(f"Unknown part type {k}")
        if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 99:
            raise DomainError(f"Keep between 0 and 99 spares of {COMPONENT_TYPES[k].name.lower()}")
        if v:
            out[k] = v
    return json.dumps(out)


def spare_minimums(session: Session) -> dict[str, int]:
    import json
    try:
        data = json.loads(get(session, "spare_minimums") or "{}")
    except ValueError:
        data = {}
    return {k: int(v) for k, v in data.items() if isinstance(v, int) and v > 0}
