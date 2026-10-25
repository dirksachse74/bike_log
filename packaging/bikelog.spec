# PyInstaller spec: one-folder build of the single launcher.
# Build from the repo root after `npm run build` in frontend/:
#     pyinstaller --noconfirm --clean packaging/bikelog.spec
# Output: dist/BikeLog/ (BikeLog.exe on Windows). User data never goes here; it lives in
# %LOCALAPPDATA%\BikeLog (or BIKELOG_DATA_DIR), and the app refuses a data dir inside the install dir.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"
if not (DIST / "index.html").exists():
    raise SystemExit("frontend/dist is missing: run `npm ci && npm run build` in frontend/ first")

# Record which commit is being built, and refuse to bundle screens built from older code (the cause
# of "I updated but Settings still shows the old Strava panel").
import json
import subprocess

try:
    COMMIT = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, timeout=10).stdout.strip() or "unknown"
except OSError:
    COMMIT = "unknown"
try:
    UI_COMMIT = json.loads((DIST / "build-info.json").read_text(encoding="utf-8")).get("commit", "unknown")
except (OSError, ValueError):
    UI_COMMIT = "missing"
if COMMIT != "unknown" and UI_COMMIT != COMMIT:
    raise SystemExit(f"frontend/dist was built from {UI_COMMIT}, but the code is at {COMMIT}. "
                     "Run `npm ci` and `npm run build` in frontend/ first, then build again.")
BUILD_INFO = Path(workpath) / "build_commit.txt"
BUILD_INFO.parent.mkdir(parents=True, exist_ok=True)
BUILD_INFO.write_text(COMMIT, encoding="utf-8")
print(f"Building Bike Log from commit {COMMIT} (screens {UI_COMMIT})")

datas = [
    (str(DIST), "bikelog/static"),                                   # resource_root()/static
    (str(BACKEND / "bikelog" / "migrations"), "bikelog/migrations"),  # resource_root()/migrations
    (str(BUILD_INFO), "bikelog"),                                    # resource_root()/build_commit.txt
]
hiddenimports = (
    collect_submodules("bikelog")
    + collect_submodules("uvicorn")       # launcher passes loop="asyncio", http="h11" explicitly
    + ["sqlalchemy.dialects.sqlite", "alembic.runtime.migration", "alembic.ddl.sqlite", "tzdata"]
)

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "httpx"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BikeLog",
    console=True,          # a window that shows the address and closes the app when closed
    icon=str(ROOT / "packaging" / "bikelog.ico") if (ROOT / "packaging" / "bikelog.ico").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BikeLog")
