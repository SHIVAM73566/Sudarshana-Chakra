"""Immutable brand identity for Sudarshana Chakra.

This module is the single source of truth for the product brand. The brand
constants are frozen (immutable dataclass + module-level tuple guard). At boot
the application calls :func:`assert_brand_integrity`, which fails closed if any
environment variable or config file attempts to override or mask the brand.

Do not add runtime overrides for these values.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Brand:
    name: str = "Sudarshana Chakra"
    codename: str = "SudarshanaChakra"
    organization: str = "Sudarshana"
    tagline: str = "Sudarshana Chakra — Immutable Edition"


BRAND = _Brand()

# Immutable public constants (module-level names are the canonical API).
BRAND_NAME = BRAND.name
APP_CODENAME = BRAND.codename
BRAND_ORG = BRAND.organization
BRAND_TAGLINE = BRAND.tagline

# Any of these appearing in env as an attempt to change the brand is fatal.
_OVERRIDE_ENV_KEYS = (
    "BRAND_NAME",
    "APP_NAME",
    "APP_BRAND",
    "SUDARSHANA_BRAND",
    "SUDARSHANA_BRAND_NAME",
    "SUDARSHANA_APP_NAME",
    "SUDARSHANA_CODENAME",
)
_OVERRIDE_JSON_KEYS = (
    "brand_name",
    "app_name",
    "app_brand",
    "brand",
    "codename",
    "product_name",
)

_CANONICAL = BRAND_NAME.casefold()


class BrandIntegrityError(RuntimeError):
    """Raised when the immutable brand is tampered with at runtime."""


def _norm(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _config_files() -> list[Path]:
    paths: list[Path] = []
    project_root = Path(__file__).resolve().parent.parent
    paths.append(project_root / "config" / "app_settings.json")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths.append(Path(local) / "SudarshanaAI" / "config" / "app_settings.json")
        paths.append(Path(local) / "Sudarshana Chakra" / "config" / "app_settings.json")
    return paths


def find_brand_tampering() -> list[str]:
    """Return tamper findings. Empty list means the brand is intact."""
    findings: list[str] = []

    for key in _OVERRIDE_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None and _norm(value) != _CANONICAL:
            findings.append(f"environment variable {key}={value!r} conflicts with brand")

    for path in _config_files():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key in _OVERRIDE_JSON_KEYS:
            if key in data and _norm(data[key]) not in ("", _CANONICAL):
                findings.append(f"{path}: '{key}'={data[key]!r} masks brand")

    return findings


def assert_brand_integrity() -> None:
    """Fail closed if the brand has been tampered with. Called at boot."""
    findings = find_brand_tampering()
    if not findings:
        return
    banner = (
        "\n" + "=" * 64 + "\n"
        f"FATAL: {BRAND_NAME} brand integrity violation. Startup aborted.\n"
        "The brand name is immutable and may not be overridden.\n"
        "- " + "\n- ".join(findings) + "\n" + "=" * 64 + "\n"
    )
    try:
        import sys

        sys.stderr.write(banner)
        sys.stderr.flush()
    except Exception:
        pass
    raise BrandIntegrityError("Brand integrity violation: refusing to start.")