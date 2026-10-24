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

datas = [
    (str(DIST), "bikelog/static"),                                   # resource_root()/static
    (str(BACKEND / "bikelog" / "migrations"), "bikelog/migrations"),  # resource_root()/migrations
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
