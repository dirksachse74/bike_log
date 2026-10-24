"""One running instance per data directory. A second launch just opens the browser on the first one."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


class AlreadyRunning(Exception):
    def __init__(self, info: dict):
        super().__init__("Bike Log is already running")
        self.info = info


class InstanceLock:
    def __init__(self, lock_file: Path, info_file: Path):
        self.lock_file, self.info_file = lock_file, info_file
        self._fh = None

    def acquire(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_file, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            info = {}
            try:
                info = json.loads(self.info_file.read_text())
            except (OSError, ValueError):
                pass
            raise AlreadyRunning(info) from None
        self._fh = fh

    def publish(self, url: str) -> None:
        self.info_file.write_text(json.dumps({"url": url, "pid": os.getpid()}))

    def release(self) -> None:
        if self._fh:
            try:
                self.info_file.unlink(missing_ok=True)
            finally:
                self._fh.close()
                self._fh = None
