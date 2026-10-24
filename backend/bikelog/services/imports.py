"""Ride import infrastructure (CSV now, Strava connector feeds the same pipeline).

Guarantees
* Identity = (source_kind, source_account, source_ref), enforced by a UNIQUE constraint. Titles,
  dates or distances are never used for identity, so a re-import never creates a second ride.
* Source values live in ride_source; local corrections (ride_override) win and are never touched.
* A ride you excluded stays excluded on every later import (inclusion is never written by imports).
* Rows before the configured import start date are skipped.
* Resumable: rows are committed in chunks together with the batch cursor. Re-running the same file
  resumes after the last committed chunk; re-running a finished file changes nothing.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from bikelog.catalog import RIDE_SPORT_TYPES
from bikelog.models import Bike, ImportBatch, Ride, RideSource
from bikelog.services import allocation, rides, settings
from bikelog.services.errors import DomainError
from bikelog.timeutil import parse_when, utc_now

TRUE = {"1", "yes", "y", "true", "ja", "x"}


# ---------------------------------------------------------------- record pipeline

def _hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def resolve_bike(session: Session, *, gear_id: str | None = None, name: str | None = None) -> int | None:
    if gear_id:
        bid = session.scalar(select(Bike.id).where(Bike.strava_gear_id == gear_id))
        if bid:
            return bid
    if name:
        return session.scalar(select(Bike.id).where(func.lower(Bike.name) == name.strip().lower()))
    return None


def upsert_record(session: Session, *, source_kind: str, source_account: str, source_ref: str, values: dict,
                  batch_id: int | None = None) -> str:
    """Insert or update one imported ride. Returns CREATED, UPDATED, UNCHANGED or SKIPPED_BEFORE_START."""
    start = settings.get(session, "import_start_date")
    tz = settings.tz(session)
    when = parse_when(values["when"], tz)
    if start and when.local_date < start:
        return "SKIPPED_BEFORE_START"
    payload_hash = _hash(values)
    src = session.scalar(select(RideSource).where(RideSource.source_kind == source_kind,
                                                  RideSource.source_account == source_account,
                                                  RideSource.source_ref == source_ref))
    if src:
        src.last_seen_at = utc_now()
        ride = session.get(Ride, src.ride_id)
        if src.payload_hash == payload_hash and ride.status == "ACTIVE":
            return "UNCHANGED"
        src.values_json = json.dumps(values)
        src.payload_hash = payload_hash
        src.import_batch_id = batch_id or src.import_batch_id
        ride.status = "ACTIVE"
        rides.apply_effective(session, ride, values)
        session.flush()
        allocation.allocate_rides(session, [ride], tz)
        return "UPDATED"
    ride = Ride(source_kind=source_kind if source_kind in ("CSV", "STRAVA") else "CSV",
                sport_type=values.get("sport_type") or "Ride")
    rides.apply_effective(session, ride, values)
    session.add(ride)
    session.flush()
    session.add(RideSource(ride_id=ride.id, source_kind=source_kind, source_account=source_account,
                           source_ref=source_ref, values_json=json.dumps(values), payload_hash=payload_hash,
                           import_batch_id=batch_id))
    session.flush()
    allocation.allocate_rides(session, [ride], tz)
    return "CREATED"


def mark_source_deleted(session: Session, source_kind: str, source_account: str, source_ref: str) -> bool:
    src = session.scalar(select(RideSource).where(RideSource.source_kind == source_kind,
                                                  RideSource.source_account == source_account,
                                                  RideSource.source_ref == source_ref))
    if not src:
        return False
    ride = session.get(Ride, src.ride_id)
    if ride.status != "SOURCE_DELETED":
        ride.status = "SOURCE_DELETED"
        allocation.allocate_rides(session, [ride], settings.tz(session))
    return True


# ---------------------------------------------------------------- CSV

class CsvFormatError(DomainError):
    pass


def _num(s: str | None, decimal_comma: bool) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    if decimal_comma:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return float(s)


def _parse_strava_date(s: str) -> str:
    dt = datetime.strptime(s.strip(), "%b %d, %Y, %I:%M:%S %p").replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_csv(content: bytes) -> tuple[str, str, list[dict]]:
    """Returns (source_kind, source_account, rows). Each row: {'row': n, 'ref', 'values'|'error'}."""
    text = content.decode("utf-8-sig")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise CsvFormatError("The file is empty")
    header = [h.strip() for h in header]
    lower = [h.lower() for h in header]
    if "activity id" in lower and "activity date" in lower:
        return "STRAVA", "strava", list(_strava_export_rows(header, reader))
    required = {"source_id", "date"}
    missing = required - set(lower)
    if missing or not ({"distance_km", "distance_mi"} & set(lower)):
        raise CsvFormatError(
            "Unrecognised CSV. Required columns: source_id, date, distance_km (or distance_mi). "
            f"Found: {', '.join(header)}")
    return "CSV", "csv", list(_generic_rows(lower, reader, decimal_comma=delimiter == ";"))


def _generic_rows(lower: list[str], reader: Iterable[list[str]], decimal_comma: bool):
    idx = {h: i for i, h in enumerate(lower)}

    def get(row, key):
        i = idx.get(key)
        return row[i].strip() if i is not None and i < len(row) and row[i].strip() else None
    for n, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        try:
            ref = get(row, "source_id")
            if not ref:
                raise ValueError("source_id is empty")
            when = get(row, "date")
            if not when:
                raise ValueError("date is empty")
            km = _num(get(row, "distance_km"), decimal_comma)
            if km is None and get(row, "distance_mi") is not None:
                km = _num(get(row, "distance_mi"), decimal_comma) * rides.KM_PER_MILE
            dur = None
            if get(row, "duration_s") is not None:
                dur = int(_num(get(row, "duration_s"), decimal_comma))
            elif get(row, "duration_min") is not None:
                dur = int(round(_num(get(row, "duration_min"), decimal_comma) * 60))
            sport = get(row, "sport_type") or "Ride"
            trainer = (get(row, "trainer") or "").lower() in TRUE
            values = {"when": when, "distance_km": km, "duration_s": dur, "name": get(row, "name"),
                      "sport_type": sport, "bike_name": get(row, "bike"),
                      "trainer": trainer or sport == "VirtualRide"}
            yield {"row": n, "ref": ref, "values": values}
        except (ValueError, TypeError) as e:
            yield {"row": n, "ref": None, "error": str(e)}


def _strava_export_rows(header: list[str], reader: Iterable[list[str]]):
    """Strava 'Download your data' activities.csv (the athlete's own export, not API data)."""
    first = {}
    for i, h in enumerate(header):
        first.setdefault(h.lower(), i)  # the export repeats some headers; the first one is in display units

    def get(row, key):
        i = first.get(key)
        return row[i].strip() if i is not None and i < len(row) and row[i].strip() else None
    for n, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        try:
            sport = get(row, "activity type") or ""
            sport_norm = sport.replace(" ", "")
            if sport_norm not in RIDE_SPORT_TYPES:
                yield {"row": n, "ref": get(row, "activity id"), "skip": "NOT_CYCLING"}
                continue
            km = _num(get(row, "distance"), False)
            elapsed = get(row, "elapsed time")
            values = {"when": _parse_strava_date(get(row, "activity date")), "distance_km": km,
                      "duration_s": int(float(elapsed)) if elapsed else None, "name": get(row, "activity name"),
                      "sport_type": sport_norm, "bike_name": get(row, "activity gear"),
                      "trainer": sport_norm == "VirtualRide"}
            yield {"row": n, "ref": get(row, "activity id"), "values": values}
        except (ValueError, TypeError) as e:
            yield {"row": n, "ref": None, "error": str(e)}


def _to_ride_values(session: Session, v: dict) -> dict:
    out = {k: v[k] for k in ("when", "distance_km", "duration_s", "name", "sport_type")}
    out["bike_id"] = resolve_bike(session, gear_id=v.get("gear_id"), name=v.get("bike_name"))
    out["usage_profile_code"] = (settings.get(session, "trainer_profile_for_virtual") or None) if v.get("trainer") else None
    return out


def run_csv_import(factory: sessionmaker[Session], content: bytes, *, file_name: str | None = None,
                   chunk_size: int = 100, on_chunk_committed: Callable[[int], None] | None = None) -> dict:
    """Import a CSV file. Each chunk commits rows and the cursor together, so a crash loses nothing."""
    sha = hashlib.sha256(content).hexdigest()
    source_kind, account, rows = parse_csv(content)
    with factory() as s, s.begin():
        batch = s.scalar(select(ImportBatch).where(ImportBatch.file_sha256 == sha, ImportBatch.status != "COMPLETED")
                         .order_by(ImportBatch.id.desc()))
        resumed = batch is not None
        if not batch:
            batch = ImportBatch(source_kind=source_kind, source_account=account, file_name=file_name,
                                file_sha256=sha, rows_total=len(rows))
            s.add(batch)
            s.flush()
        else:
            batch.status = "RUNNING"
        batch_id, cursor = batch.id, batch.cursor_row
        counts = json.loads(batch.counts_json or "{}")
    errors: list[dict] = counts.pop("errors", []) if isinstance(counts.get("errors"), list) else []
    try:
        for start in range(cursor, len(rows), chunk_size):
            chunk = rows[start:start + chunk_size]
            with factory() as s, s.begin():
                for r in chunk:
                    if "error" in r:
                        counts["ERROR"] = counts.get("ERROR", 0) + 1
                        errors.append({"row": r["row"], "error": r["error"]})
                        continue
                    if "skip" in r:
                        counts["SKIPPED_" + r["skip"]] = counts.get("SKIPPED_" + r["skip"], 0) + 1
                        continue
                    try:
                        with s.begin_nested():
                            res = upsert_record(s, source_kind=source_kind, source_account=account,
                                                source_ref=r["ref"], values=_to_ride_values(s, r["values"]),
                                                batch_id=batch_id)
                    except (ValueError, DomainError) as e:
                        res = "ERROR"
                        errors.append({"row": r["row"], "error": getattr(e, "message", str(e))})
                    counts[res] = counts.get(res, 0) + 1
                b = s.get(ImportBatch, batch_id)
                b.cursor_row = start + len(chunk)
                b.counts_json = json.dumps({**counts, "errors": errors[-50:]})
            if on_chunk_committed:
                on_chunk_committed(start + len(chunk))
    except Exception as e:
        with factory() as s, s.begin():
            b = s.get(ImportBatch, batch_id)
            b.status, b.error = "FAILED", str(e)[:500]
        raise
    with factory() as s, s.begin():
        b = s.get(ImportBatch, batch_id)
        b.status, b.finished_at = "COMPLETED", utc_now()
        b.counts_json = json.dumps({**counts, "errors": errors[-50:]})
    return {"batch_id": batch_id, "source_kind": source_kind, "resumed": resumed, "rows": len(rows),
            "counts": counts, "errors": errors[-50:]}


def list_batches(session: Session, limit: int = 20) -> list[dict]:
    out = []
    for b in session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit)):
        counts = json.loads(b.counts_json or "{}")
        out.append({"id": b.id, "source_kind": b.source_kind, "file_name": b.file_name, "status": b.status,
                    "rows_total": b.rows_total, "cursor_row": b.cursor_row, "counts": counts,
                    "error": b.error, "started_at": b.started_at, "finished_at": b.finished_at})
    return out


CSV_TEMPLATE = (
    "source_id,date,distance_km,duration_min,name,bike,sport_type,trainer\n"
    "garmin-2026-10-05-1,2026-10-05,62.4,128,Taunus loop,TIME NXR,Ride,no\n"
    "zwift-2026-10-07,2026-10-07T18:30,35.0,60,Zwift race,TIME NXR,VirtualRide,yes\n"
)
