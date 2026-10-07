"""Immutable brand-logo binding for Sudarshana Chakra.

The primary brand logo, the square application icon and the browser favicon are
permanent, locked assets. Their bytes are embedded in
:mod:`core.brand_logo_asset` and verified/re-written at boot, so the graphics
cannot be silently deleted, swapped or replaced by a downstream user.

There is intentionally **no** setting, environment variable or API to rename,
override or delete the core logo. If an integrity check ever finds the file
missing or altered it is automatically restored from the embedded original.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from pathlib import Path

from core.brand_logo_asset import (
    FAVICON_BYTES_B64,
    FAVICON_SHA256,
    ICON_BYTES_B64,
    ICON_SHA256,
    LOGO_BYTES_B64,
    LOGO_HEIGHT,
    LOGO_SHA256,
    LOGO_WIDTH,
)

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

LOGO_ASSET = ASSETS_DIR / "sudarshana_chakra_ai_logo.png"
ICON_ASSET = ASSETS_DIR / "app_icon_core.png"
FAVICON_ASSET = ASSETS_DIR / "favicon.ico"

# Canonical, relative web path used by HTML dashboards and front-end markup.
WEB_LOGO_PATH = "/assets/sudarshana_chakra_ai_logo.png"
WEB_ICON_PATH = "/assets/app_icon_core.png"
WEB_FAVICON_PATH = "/assets/favicon.ico"

_NATIVE_BANNER_ASPECT = LOGO_WIDTH / LOGO_HEIGHT if LOGO_HEIGHT else 16 / 9

_ASSETS = (
    (LOGO_ASSET, LOGO_BYTES_B64, LOGO_SHA256),
    (ICON_ASSET, ICON_BYTES_B64, ICON_SHA256),
    (FAVICON_ASSET, FAVICON_BYTES_B64, FAVICON_SHA256),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_writeable(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass


def _make_readonly(path: Path) -> None:
    try:
        path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass


def _file_matches(path: Path, expected_sha: str) -> bool:
    try:
        return path.is_file() and _sha256(path.read_bytes()) == expected_sha
    except Exception:
        return False


def logo_asset_matches() -> bool:
    return _file_matches(LOGO_ASSET, LOGO_SHA256)


def icon_asset_matches() -> bool:
    return _file_matches(ICON_ASSET, ICON_SHA256)


def favicon_asset_matches() -> bool:
    return _file_matches(FAVICON_ASSET, FAVICON_SHA256)


def assets_match() -> bool:
    return logo_asset_matches() and icon_asset_matches() and favicon_asset_matches()


def ensure_brand_assets() -> Path:
    """Restore any missing/altered brand asset from the embedded original.

    Returns the primary logo path. Never raises. Restored files are marked
    read-only so they cannot be casually overwritten.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for path, b64, sha in _ASSETS:
        if _file_matches(path, sha):
            continue
        try:
            data = base64.b64decode(b64)
            _make_writeable(path)
            path.write_bytes(data)
            _make_readonly(path)
        except Exception:
            pass
    return LOGO_ASSET


def assert_brand_asset_integrity() -> None:
    """Self-heal the brand assets at boot, then fail closed only if the
    *primary* logo could not be restored (e.g. read-only filesystem)."""
    ensure_brand_assets()
    if logo_asset_matches():
        return
    raise RuntimeError("Brand logo integrity violation: could not restore the immutable logo.")


def logo_aspect_ratio() -> float:
    """Native aspect ratio of the installed primary logo."""
    return _NATIVE_BANNER_ASPECT


def get_logo_pixmap(max_width: int, max_height: int):
    """Return a QPixmap of the locked logo fitted within the given box.

    The glow/brand look is preserved by smooth, aspect-preserving scaling.
    PyQt is imported lazily so this module stays import-cheap at boot.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap

    ensure_brand_assets()
    pix = QPixmap(str(LOGO_ASSET))
    if pix.isNull():
        return pix
    return pix.scaled(
        max_width,
        max_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def get_app_icon():
    """Return the locked QIcon (square app icon, falling back to the logo)."""
    from PyQt6.QtGui import QIcon

    ensure_brand_assets()
    if ICON_ASSET.is_file():
        return QIcon(str(ICON_ASSET))
    return QIcon(str(LOGO_ASSET))


def apply_window_icon(window) -> None:
    """Apply the locked brand icon to any QWidget/QWindow instance."""
    try:
        window.setWindowIcon(get_app_icon())
    except Exception:
        pass