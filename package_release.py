"""Build a clean, distributable source release ZIP for Sudarshana Chakra.

Usage:
    python package_release.py [--out dist]

Excludes developer junk, virtual environments, git metadata, caches,
secrets and personal runtime configuration so the resulting archive is
safe to hand off as a "ready to use" release.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DIR_EXCLUDES = {
    ".git", ".venv", "venv", "env", "ENV",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".gradle", ".idea", ".cxx", ".vscode",
    "build", "dist", "build_setup", "scratch", "release",
    "ig_browser_profile", "browser_profile", "patch_backups", "ppt_template_cache",
    "tests", ".github",
}

FILE_EXCLUDES = {
    ".env", ".ds_store", "thumbs.db", "ig_debug.log",
    "api_keys.json", "email_credentials.json", "identity.json",
    "learned_rules.json", "organizer_history.json", "patch_history.json",
    "sudarshana_connect.json", "devices.json", "ig_session.json",
    "local.properties", "voice_security.json", "app_settings.json",
    ".desktop_shortcut_created",
    "pytest.ini", "conftest.py", "tox.ini", "setup.cfg",
    "package_release.py", "startup.log",
}

FILE_GLOBS = (
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.log", "*.bak", "*.tmp",
    "*.sqlite3", "*.key", "*.apk", "*.aab", "*.zip", "*.spec",
    "test_*.py", "*_test.py", "conftest.py",
)


def read_version() -> str:
    try:
        text = (ROOT / "version.txt").read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+)", text)
        if m:
            return ".".join(m.groups())
    except Exception:
        pass
    return "1.0.0"


def is_excluded(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts}
    if parts & {d.lower() for d in DIR_EXCLUDES}:
        return True
    name = rel.name.lower()
    if name in FILE_EXCLUDES:
        return True
    return any(fnmatch.fnmatch(name, g) for g in FILE_GLOBS)


def build(out_dir: Path) -> Path:
    version = read_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"Sudarshana_Chakra_AI_v{version}.zip"

    arc_root = f"Sudarshana_Chakra_AI_v{version}"
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if is_excluded(rel):
                continue
            zf.write(path, arcname=str(Path(arc_root) / rel))
            count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Packaged {count} files -> {zip_path}")
    print(f"Archive size: {size_mb:.2f} MB")
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Sudarshana Chakra release ZIP.")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist)")
    args = ap.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    build(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())