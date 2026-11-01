"""Make a Bike Log release: raise the version, date the changelog, commit and tag.

    .venv/bin/python scripts/release.py patch      # 0.2.0 -> 0.2.1  (fixes only)
    .venv/bin/python scripts/release.py minor      # 0.2.0 -> 0.3.0  (new features)
    .venv/bin/python scripts/release.py major      # 0.2.0 -> 1.0.0  (big change, e.g. data format)
    add --dry-run to only show what would change, --push to push the branch and the tag afterwards

What it does, in order (and stops before changing anything if a check fails):
1. checks: clean working tree, not on main/master, CHANGELOG.md has entries under "## Unreleased";
2. writes the new number into backend/bikelog/__init__.py (the one source of the version) and
   frontend/package.json (+ lock file), and turns "## Unreleased" into "## X.Y.Z (date)" with a fresh empty
   "## Unreleased" above it;
3. commits "Release X.Y.Z" and creates the tag vX.Y.Z on that commit.
A build of that tagged commit shows the plain version ("0.3.0"); later commits show "0.3.0+<commit>".
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = Path("backend/bikelog/__init__.py")
PACKAGE = Path("frontend/package.json")
LOCK = Path("frontend/package-lock.json")
CHANGELOG = Path("CHANGELOG.md")
VERSION_RE = re.compile(r'__version__ = "(\d+)\.(\d+)\.(\d+)"')
UNRELEASED = "## Unreleased"


def current(root: Path) -> str:
    m = VERSION_RE.search((root / INIT).read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"No __version__ = \"X.Y.Z\" in {INIT}")
    return ".".join(m.groups())


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(part)


def unreleased_notes(changelog: str) -> str:
    if UNRELEASED not in changelog:
        raise SystemExit(f"CHANGELOG.md has no '{UNRELEASED}' section")
    body = changelog.split(UNRELEASED, 1)[1]
    nxt = re.search(r"^## ", body, flags=re.M)
    return (body[: nxt.start()] if nxt else body).strip()


def write_files(root: Path, new: str, today: date) -> None:
    init = root / INIT
    init.write_text(VERSION_RE.sub(f'__version__ = "{new}"', init.read_text(encoding="utf-8"), count=1),
                    encoding="utf-8")
    for rel in (PACKAGE, LOCK):
        f = root / rel
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        data["version"] = new
        if "" in data.get("packages", {}):
            data["packages"][""]["version"] = new
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cl = root / CHANGELOG
    text = cl.read_text(encoding="utf-8")
    cl.write_text(text.replace(UNRELEASED, f"{UNRELEASED}\n\n## {new} ({today.isoformat()})", 1), encoding="utf-8")


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part", choices=("major", "minor", "patch"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true", help="push the branch and the tag to origin")
    args = ap.parse_args(argv)

    old = current(ROOT)
    new = bump(old, args.part)
    notes = unreleased_notes((ROOT / CHANGELOG).read_text(encoding="utf-8"))
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    problems = []
    if branch in ("main", "master"):
        problems.append(f"you are on {branch}; releases are made on the feature branch")
    if git("status", "--porcelain", "--untracked-files=no"):
        problems.append("there are uncommitted changes; commit or restore them first")
    if not notes:
        problems.append("CHANGELOG.md has nothing under '## Unreleased'; describe the changes first")
    if git("tag", "--list", f"v{new}"):
        problems.append(f"tag v{new} already exists")
    print(f"Release {old} -> {new} on branch {branch}\n\nChanges:\n{notes or '(none)'}\n")
    if problems:
        print("Not released:\n- " + "\n- ".join(problems))
        return 1
    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0
    write_files(ROOT, new, date.today())
    git("add", str(INIT), str(PACKAGE), str(LOCK), str(CHANGELOG))
    git("commit", "-m", f"Release {new}")
    git("tag", "-a", f"v{new}", "-m", f"Bike Log {new}")
    print(f"Committed 'Release {new}' and tagged v{new}.")
    if args.push:
        git("push", "origin", branch)
        git("push", "origin", f"v{new}")
        print("Pushed the branch and the tag.")
    else:
        print(f"To publish: git push origin {branch}; git push origin v{new}")
    print("Then build: packaging\\build.ps1 (the installer will be BikeLog-" + new + "-setup.exe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
