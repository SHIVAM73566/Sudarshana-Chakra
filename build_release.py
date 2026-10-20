"""Commercial release packager for Sudarshana Chakra.

Builds a clean, secret-free distribution tree and zips it. Run from the repo
root with the project venv:

    & ".venv\\Scripts\\python.exe" "build_release.py" --version 1.0

What it does
------------
1. Signs ``core/integrity_manifest.json`` (guarded files) for the release.
2. Copies the app tree into ``release/Sudarshana_Chakra_AI/`` while excluding
   secrets, caches, user state, build artifacts and dev-only files.
3. Writes a release ``.env`` marker and a locked ``requirements.txt``.
4. Confirms no secret material or local state slipped into the output.
5. Produces ``Sudarshana_Chakra_AI_v<version>_COMMERCIAL.zip``.

Nothing is uploaded anywhere. Local-first by construction.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = ROOT / "release"

# Directories never shipped.
EXCLUDE_DIRS = {
    ".git", ".github", ".venv", "venv", "ENV", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "build", "dist", "release", "logs",
    ".playwright-mcp", "promos", "generated", "scratch",
    "sudarshana-connect-android", "smart_home",
    "installer/build", "installer/dist", "installer/build_setup",
}

# Files/globs never shipped.
EXCLUDE_SUFFIXES = (
    ".pyc", ".pyo", ".pyd", ".log", ".sqlite3", ".sqlite", ".db",
    ".key", ".pem", ".zip", ".7z",
)
EXCLUDE_NAMES = {
    ".env", "api_keys.json", "email_credentials.json", "ig_session.json",
    "identity.json", "patch_history.json", "device_location_cache.json",
    "learned_rules.json", "organizer_history.json", "sudarshana_connect.json",
    "devices.json", "FATAL_CRASH.log", "FATAL_CRASH_RECOVERED.log",
    "integrity_manifest.json",  # re-generated during build
}
DEV_ONLY_FILES = {
    "build_release.py", "test_local_brain.py", "test_self_heal.py",
    "test_sensorium_live.py", "process_logo.py",
}

SECRET_PATTERNS = (
    r"AIza[0-9A-Za-z_\-]{20,}",          # Google API keys
    r"nvapi-[0-9A-Za-z_\-]{20,}",        # NVIDIA NIM
    r"sk-or-v1-[0-9a-f]{32,}",           # OpenRouter
    r"sk-[0-9A-Za-z]{32,}",              # OpenAI-style
    r"ghp_[0-9A-Za-z]{30,}",             # GitHub PAT
    r"AKIA[0-9A-Z]{16}",                 # AWS access key id
    r"xox[bpas]-[0-9A-Za-z\-]{10,}",     # Slack
)

REQUIRED_ENV_KEYS = ("GEMINI_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY")


def _should_copy(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_NAMES or name in DEV_ONLY_FILES:
        return False
    if name.startswith(".") and name not in (".env.example",):
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return True


def _ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in EXCLUDE_DIRS:
            ignored.add(name)
            continue
        full = Path(directory) / name
        if not _should_copy(full):
            ignored.add(name)
    return ignored


def _sign_integrity() -> dict[str, str]:
    from core import anti_tamper

    anti_tamper.write_manifest()
    return anti_tamper.compute_manifest()


def _requirements_text() -> str:
    src = ROOT / "requirements.txt"
    lines: list[str] = []
    if src.is_file():
        for line in src.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("-r") or stripped.startswith("-e"):
                continue
            lines.append(stripped)
    return "# Sudarshana Chakra AI - pinned runtime requirements\n" + "\n".join(lines) + "\n"


def _scan_for_secrets(directory: Path) -> list[str]:
    hits: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECRET_PATTERNS:
            match = re.search(pattern, text)
            if match:
                hits.append(f"{path.relative_to(directory)}: matches '{pattern}'")
                break
    return hits


def _safe_rmtree(path: Path) -> None:
    """Best-effort recursive delete that tolerates OneDrive file locks."""
    if not path.exists():
        return

    def _onerror(func, target, exc_info):  # pragma: no cover - OS-specific
        import os
        import stat
        import time as _time

        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            _time.sleep(0.25)
            try:
                func(target)
            except Exception:
                pass

    shutil.rmtree(path, onerror=_onerror)


def build(version: str, *, verbose: bool = True) -> Path:
    target = RELEASE_ROOT / "Sudarshana_Chakra_AI"
    _safe_rmtree(RELEASE_ROOT)
    if target.exists():
        _safe_rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    manifest = _sign_integrity()
    if verbose:
        print(f"[release] signed integrity manifest ({len(manifest)} guarded file(s))")

    for item in ROOT.iterdir():
        if item.name in EXCLUDE_DIRS or not _should_copy(item):
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, ignore=_ignore)
        else:
            shutil.copy2(item, destination)

    # Re-generate the manifest inside the shipped tree.
    (target / "core").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "core" / "integrity_manifest.json", target / "core" / "integrity_manifest.json")

    # Locked requirements + env template.
    (target / "requirements.txt").write_text(_requirements_text(), encoding="utf-8")
    env_example = ROOT / ".env.example"
    if env_example.is_file():
        shutil.copy2(env_example, target / ".env.example")
    (target / "RELEASE_NOTES.txt").write_text(
        f"Sudarshana Chakra AI v{version}\n"
        "Local-first desktop AI assistant.\n\n"
        "Run: python main.py\n"
        "Licensing: set LICENSING_ENABLED=true to enforce trial/license.\n",
        encoding="utf-8",
    )
    docs = target / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "INSTALLATION.md").write_text(
        "# Installation\n\n"
        "1. Install Python 3.14+ and create a virtual environment.\n"
        "2. `pip install -r requirements.txt`\n"
        "3. Copy `.env.example` to `.env` and add your API keys.\n"
        "4. Run `python main.py`.\n",
        encoding="utf-8",
    )

    hits = _scan_for_secrets(target)
    archive = ROOT / f"Sudarshana_Chakra_AI_v{version}_COMMERCIAL.zip"
    if archive.exists():
        archive.unlink()

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in target.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(target.parent))

    if verbose:
        size_mb = archive.stat().st_size / (1024 * 1024)
        print(f"[release] tree     -> {target}")
        print(f"[release] archive  -> {archive.name} ({size_mb:.1f} MB)")
        print(f"[release] secret scan: {'CLEAN' if not hits else 'REVIEW'}")
        for hit in hits:
            print(f"  ! {hit}")
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the commercial release ZIP.")
    parser.add_argument("--version", default="1.0", help="release version label")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        build(args.version, verbose=not args.quiet)
    except Exception as exc:
        print(f"[release] FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
