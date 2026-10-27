"""One version number everywhere, release vs in-between builds, and the release script."""
import json
import sys
from datetime import date
from pathlib import Path

from bikelog import __version__, buildinfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import release  # noqa: E402


def test_version_is_semver_and_the_same_everywhere():
    parts = __version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
    assert json.loads((ROOT / "frontend/package.json").read_text())["version"] == __version__
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    assert lock["version"] == __version__ and lock["packages"][""]["version"] == __version__
    assert release.current(ROOT) == __version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__} (" in changelog and "## Unreleased" in changelog


def test_release_build_shows_plain_version_other_builds_show_commit():
    assert buildinfo.display_version("0.2.0", "abc1234", ["v0.2.0"]) == "0.2.0"
    assert buildinfo.display_version("0.2.0", "def5678", []) == "0.2.0+def5678"
    assert buildinfo.display_version("0.2.0", "def5678", ["v0.1.0"]) == "0.2.0+def5678"
    assert buildinfo.display_version("0.2.0", "unknown", None) == "0.2.0+unknown"
    assert buildinfo.full_version().startswith(__version__)


def test_bump_and_write_files(tmp_path):
    assert release.bump("0.2.0", "patch") == "0.2.1"
    assert release.bump("0.2.9", "minor") == "0.3.0"
    assert release.bump("0.3.4", "major") == "1.0.0"
    (tmp_path / "backend/bikelog").mkdir(parents=True)
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/bikelog/__init__.py").write_text('"""x"""\n__version__ = "0.2.0"\n')
    (tmp_path / "frontend/package.json").write_text(json.dumps({"name": "f", "version": "0.2.0"}))
    (tmp_path / "frontend/package-lock.json").write_text(json.dumps({"version": "0.2.0",
                                                                     "packages": {"": {"version": "0.2.0"}}}))
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- Fixed a thing\n\n## 0.2.0 (2026-10-25)\n\nold\n")
    assert release.unreleased_notes((tmp_path / "CHANGELOG.md").read_text()) == "- Fixed a thing"
    release.write_files(tmp_path, "0.2.1", date(2026, 11, 1))
    assert release.current(tmp_path) == "0.2.1"
    assert json.loads((tmp_path / "frontend/package.json").read_text())["version"] == "0.2.1"
    lock = json.loads((tmp_path / "frontend/package-lock.json").read_text())
    assert lock["packages"][""]["version"] == "0.2.1"
    cl = (tmp_path / "CHANGELOG.md").read_text()
    assert "## Unreleased\n\n## 0.2.1 (2026-11-01)\n\n- Fixed a thing" in cl
    assert release.unreleased_notes(cl) == ""
