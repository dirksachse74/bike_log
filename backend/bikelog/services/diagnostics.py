"""Read the diagnostic log for the Settings page. Lines are redacted again on the way out, so even a
secret that slipped into an old log line is never shown or downloaded."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from bikelog.logging_setup import redact
from bikelog.paths import DataPaths

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def log_file(paths: DataPaths) -> Path:
    return paths.logs / "bikelog.log"


def _files(paths: DataPaths) -> list[Path]:
    """Oldest first: bikelog.log.5 … bikelog.log.1, bikelog.log (rotating handler names)."""
    rotated = sorted(paths.logs.glob("bikelog.log.*"), key=lambda p: -int(p.suffix[1:]) if p.suffix[1:].isdigit() else 0)
    current = log_file(paths)
    return rotated + ([current] if current.exists() else [])


def tail(paths: DataPaths, lines: int = 300, min_level: str = "INFO") -> dict:
    lines = max(1, min(lines, 5000))
    floor = LEVELS.index(min_level) if min_level in LEVELS else 1
    keep: deque[str] = deque(maxlen=lines)
    for f in _files(paths):
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                parts = line.split(None, 3)
                level = parts[2] if len(parts) > 2 else ""
                # continuation lines (tracebacks) have no level: keep them with their entry
                if level in LEVELS and LEVELS.index(level) < floor:
                    continue
                keep.append(redact(line))
    files = _files(paths)
    return {"directory": str(paths.logs), "file": str(log_file(paths)), "lines": list(keep),
            "size_bytes": sum(f.stat().st_size for f in files), "files": [f.name for f in files]}


def full_text(paths: DataPaths) -> str:
    out = []
    for f in _files(paths):
        out.append(redact(f.read_text(encoding="utf-8", errors="replace")))
    return "".join(out)
