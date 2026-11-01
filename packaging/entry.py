"""PyInstaller entry point: the single launcher (BikeLog.exe on Windows)."""
from bikelog.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
