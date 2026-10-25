"""Which code is running: the git commit of the backend and of the bundled screens (frontend).

A packaged build gets ``build_commit.txt`` from the PyInstaller spec; a development run asks git. The
frontend build writes ``build-info.json`` into its dist folder (vite.config.ts). Settings shows both, so
a stale frontend or an old copy of the app that is still running is visible at a glance.
"""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from bikelog.paths import is_frozen, resource_root

UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def commit() -> str:
    f = resource_root() / "build_commit.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip() or UNKNOWN
    if is_frozen():
        return UNKNOWN
    try:
        out = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or UNKNOWN
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN


def ui_commit(static_dir: Path | None) -> str:
    if static_dir is None:
        return UNKNOWN
    try:
        return json.loads((static_dir / "build-info.json").read_text(encoding="utf-8")).get("commit") or UNKNOWN
    except (OSError, ValueError):
        return UNKNOWN
