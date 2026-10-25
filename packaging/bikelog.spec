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
# Version: the number comes from bikelog.__version__ (the only place it is written). A build of the
# commit tagged vX.Y.Z is a release ("0.2.0"); anything else carries the commit ("0.2.0+abc1234").
import re

VERSION = re.search(r'__version__ = "([^"]+)"', (BACKEND / "bikelog" / "__init__.py").read_text(encoding="utf-8")).group(1)
try:
    TAGS = subprocess.run(["git", "tag", "--points-at", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          timeout=10).stdout.split()
except OSError:
    TAGS = []
FULL_VERSION = VERSION if f"v{VERSION}" in TAGS else f"{VERSION}+{COMMIT}"
WORK = Path(workpath)
WORK.mkdir(parents=True, exist_ok=True)
BUILD_INFO = WORK / "build_commit.txt"
BUILD_INFO.write_text(COMMIT, encoding="utf-8")
BUILD_VERSION = WORK / "build_version.txt"
BUILD_VERSION.write_text(FULL_VERSION, encoding="utf-8")
print(f"Building Bike Log {FULL_VERSION} from commit {COMMIT} (screens {UI_COMMIT})")

# Windows file properties of BikeLog.exe (Explorer → Properties → Details). The helper needs pefile,
# which PyInstaller installs on Windows only; elsewhere the exe simply has no version resource.
try:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    NUMS = tuple(int(x) for x in VERSION.split(".")) + (0,)
    VERSION_INFO = VSVersionInfo(
        ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Dirk Sachse"),
                StringStruct("FileDescription", "Bike Log"),
                StringStruct("FileVersion", FULL_VERSION),
                StringStruct("InternalName", "BikeLog"),
                StringStruct("OriginalFilename", "BikeLog.exe"),
                StringStruct("ProductName", "Bike Log"),
                StringStruct("ProductVersion", FULL_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
except ImportError:
    VERSION_INFO = None
except Exception as e:  # never let file properties break a build; the app itself still knows its version
    print(f"WARNING: Windows file version info skipped: {e}")
    VERSION_INFO = None

datas = [
    (str(DIST), "bikelog/static"),                                   # resource_root()/static
    (str(BACKEND / "bikelog" / "migrations"), "bikelog/migrations"),  # resource_root()/migrations
    (str(BUILD_INFO), "bikelog"),                                    # resource_root()/build_commit.txt
    (str(BUILD_VERSION), "bikelog"),                                 # resource_root()/build_version.txt
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
    version=VERSION_INFO,  # file version shown by Windows; ignored on other systems
    icon=str(ROOT / "packaging" / "bikelog.ico") if (ROOT / "packaging" / "bikelog.ico").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BikeLog")
