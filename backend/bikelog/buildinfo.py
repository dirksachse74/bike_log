"""Which code is running: the version, the git commit of the backend and of the bundled screens.

Versioning: ``bikelog.__version__`` (MAJOR.MINOR.PATCH) is the one place the version number is written;
``scripts/release.py`` raises it, updates CHANGELOG.md and tags the commit ``vX.Y.Z``. A build of exactly
that tagged commit is a *release* and shows "0.2.0"; any other build shows the commit as build metadata,
"0.2.0+abc1234" (semantic versioning: 0.2.0 plus later, unreleased commits).

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
    return _git("rev-parse", "--short=7", "HEAD") or UNKNOWN


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def display_version(version: str, commit_id: str, tags: list[str] | None) -> str:
    """'0.2.0' for the tagged release commit, otherwise '0.2.0+<commit>'."""
    if tags is not None and f"v{version}" in tags:
        return version
    return f"{version}+{commit_id}" if commit_id and commit_id != UNKNOWN else f"{version}+unknown"


@lru_cache(maxsize=1)
def full_version() -> str:
    from bikelog import __version__
    f = resource_root() / "build_version.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip() or __version__
    if is_frozen():
        return __version__
    tags = _git("tag", "--points-at", "HEAD")
    return display_version(__version__, commit(), tags.split() if tags is not None else None)


def is_release() -> bool:
    return "+" not in full_version()


def _ui_info(static_dir: Path | None) -> dict:
    if static_dir is None:
        return {}
    try:
        return json.loads((static_dir / "build-info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ui_commit(static_dir: Path | None) -> str:
    return _ui_info(static_dir).get("commit") or UNKNOWN


def ui_version(static_dir: Path | None) -> str:
    return _ui_info(static_dir).get("version") or UNKNOWN
