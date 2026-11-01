"""Write the text of a GitHub Release: install note for friends + what changed in this version.

    python scripts/release_notes.py 0.3.0 [--sha256 HEX] [--file BikeLog-0.3.0-setup.exe] > notes.md

Used by .github/workflows/release.yml. The changes come from the "## 0.3.0 (date)" part of CHANGELOG.md,
or from "## Unreleased" if that version has no part yet. The install note is docs/INSTALL.md without
its first heading, so friends can read it even when the code repository is private.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_CHANGES = 90_000  # GitHub allows 125 000 characters in a release text


def changelog_section(changelog: str, version: str) -> str:
    """The body of the '## <version> (...)' section, else of '## Unreleased', else ''."""
    for head in (rf"## {re.escape(version)}\b[^\n]*", r"## Unreleased[^\n]*"):
        m = re.search(rf"^{head}\n(.*?)(?=^## |\Z)", changelog, flags=re.M | re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def install_note(text: str) -> str:
    return re.sub(r"\A# [^\n]*\n+", "", text).strip()


def build(version: str, sha256: str | None = None, file: str | None = None, root: Path = ROOT) -> str:
    changes = changelog_section((root / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if len(changes) > MAX_CHANGES:
        changes = changes[:MAX_CHANGES].rsplit("\n", 1)[0] + "\n\n… (shortened; the full list is in CHANGELOG.md)"
    parts = [
        f"**Download:** `{file or f'BikeLog-{version}-setup.exe'}` below under **Assets**, run it. "
        "Updating over an older version keeps your data.",
        install_note((root / "docs" / "INSTALL.md").read_text(encoding="utf-8")),
        f"<details><summary>What changed in {version}</summary>\n\n{changes or '(no entries)'}\n\n</details>",
    ]
    if sha256:
        parts.append(f"<sub>SHA-256 of the installer: `{sha256}`</sub>")
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("version")
    ap.add_argument("--sha256")
    ap.add_argument("--file")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(build(a.version, a.sha256, a.file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
