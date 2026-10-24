"""Where the app keeps its files.

Program files (code, frontend assets, migrations) live next to the executable and are
replaced on every upgrade. User data (database, attachments, backups, logs) lives in a
per-user data directory that installers and upgrades never touch.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Folder holding bundled read-only resources (static assets, migrations)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "bikelog"
    return Path(__file__).resolve().parent


def install_dir() -> Path | None:
    return Path(sys.executable).resolve().parent if is_frozen() else None


def default_data_dir() -> Path:
    override = os.environ.get("BIKELOG_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BikeLog"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BikeLog"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "bikelog"


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "data" / "bikelog.db"

    @property
    def attachments(self) -> Path:
        return self.root / "attachments"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def lock_file(self) -> Path:
        return self.root / "bikelog.lock"

    @property
    def instance_file(self) -> Path:
        return self.root / "instance.json"

    def ensure(self) -> "DataPaths":
        inst = install_dir()
        if inst is not None and (self.root == inst or inst in self.root.parents):
            raise RuntimeError(f"Data directory {self.root} must not be inside the installation directory {inst}")
        for p in (self.database.parent, self.attachments, self.backups, self.exports, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self


def data_paths(root: Path | None = None) -> DataPaths:
    return DataPaths(root or default_data_dir()).ensure()
