# core/env.py
"""Minimal .env loader for Sudarshana Chakra.

Reads <project root>/.env and exports KEY=VALUE pairs into os.environ
without overriding already-set environment variables. Natively supports
writing GEMINI_API_KEY / NVIDIA_API_KEY so credentials are never hardcoded.

No third-party dependency is required.
"""

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def get_base_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


ENV_PATH = get_base_dir() / ".env"


def load_dotenv(path: str | Path | None = None) -> bool:
    """Load KEY=VALUE pairs from a .env file into os.environ (never overrides)."""
    env_file = Path(path) if path else ENV_PATH
    if not env_file.exists():
        return False
    loaded_any = False
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value
            loaded_any = True
    return loaded_any


def write_key(key: str, value: str, path: str | Path | None = None) -> bool:
    """Replace or append KEY=VALUE inside the .env file. Empty values are skipped."""
    value = (value or "").strip()
    if not value:
        return False
    env_file = Path(path) if path else ENV_PATH
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        match = _KEY_RE.match(line)
        if match and match.group(1) == key:
            if not replaced:
                new_lines.append(f"{key}={value}")
                replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    os.environ[key] = value
    return True