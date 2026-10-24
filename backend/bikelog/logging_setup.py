"""Diagnostic logging to a rotating file in the data directory, with secrets redacted."""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

_PATTERNS = [
    # key=value / "key": "value" style secrets
    re.compile(r"(?i)((?:access|refresh)_token|client_secret|secret|password|api[_-]?key|x-bikelog-token|authorization)"
               r"(\"?\s*[:=]\s*\"?)(?:bearer\s+)?([^\s\"&,;]+)"),
    # the CSRF token as injected into HTML
    re.compile(r"(name=\"bikelog-token\" content=\")([^\"]+)(\")"),
]


def redact(text: str) -> str:
    text = _PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)}[REDACTED]{m.group(3)}", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # malformed args: keep the record, don't crash logging
            return True
        record.msg = redact(msg)
        record.args = None
        return True


LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: int = logging.INFO, console: bool = True) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bikelog.log"
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter(LOG_FORMAT)
    fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handlers: list[logging.Handler] = [fh]
    if console:
        handlers.append(logging.StreamHandler())
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    # uvicorn's access log would print every request; keep it at warning
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return log_file
