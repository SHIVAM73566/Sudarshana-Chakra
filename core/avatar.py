"""Immutable companion-avatar binding for Sudarshana Chakra.

The avatar portrait is a permanent, locked asset. Its bytes are embedded in
``core.avatar_asset`` and re-written/verified at boot, so the image cannot be
silently deleted, swapped or replaced by a downstream user. Only the avatar's
*display name* is user-customisable; the photo never is.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from pathlib import Path

from core.avatar_asset import AVATAR_BYTES_B64, AVATAR_SHA256

BASE_DIR = Path(__file__).resolve().parent.parent
AVATAR_ASSET = BASE_DIR / "assets" / "sudarshana_avatar_core.png"

# Presented wherever the avatar is pinned.
AVATAR_LABEL = "\U0001F512 System Avatar (Locked / Permanent)"
DEFAULT_DISPLAY_NAME = "Guardian Avatar"
DISPLAY_NAME_SETTING_KEY = "avatar_display_name"
DISPLAY_NAME_MAX_LEN = 40

# Callbacks notified when the display name changes (keeps the avatar portal in sync).
_name_listeners: list = []


def register_name_listener(fn) -> None:
    if callable(fn) and fn not in _name_listeners:
        _name_listeners.append(fn)


def _notify_name(name: str) -> None:
    for fn in list(_name_listeners):
        try:
            fn(name)
        except Exception:
            pass


def _embedded_bytes() -> bytes:
    return base64.b64decode(AVATAR_BYTES_B64)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def avatar_asset_matches() -> bool:
    """True if the on-disk asset exactly matches the embedded original."""
    try:
        return AVATAR_ASSET.is_file() and _sha256(AVATAR_ASSET.read_bytes()) == AVATAR_SHA256
    except Exception:
        return False


def ensure_avatar_asset() -> Path:
    """Restore the locked avatar if it is missing, altered or replaced. Read-only."""
    if not avatar_asset_matches():
        data = _embedded_bytes()
        AVATAR_ASSET.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(AVATAR_ASSET, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
        AVATAR_ASSET.write_bytes(data)
    try:
        os.chmod(AVATAR_ASSET, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass
    return AVATAR_ASSET


def get_display_name() -> str:
    """Return the (user-customisable) avatar display name."""
    try:
        from memory import config_manager

        value = config_manager.get_setting(DISPLAY_NAME_SETTING_KEY, DEFAULT_DISPLAY_NAME)
        value = (str(value).strip() or DEFAULT_DISPLAY_NAME)[:DISPLAY_NAME_MAX_LEN]
        return value
    except Exception:
        return DEFAULT_DISPLAY_NAME


def set_display_name(name: str) -> str:
    """Persist a new display name. Never affects the locked photo asset."""
    clean = (str(name or "").strip() or DEFAULT_DISPLAY_NAME)[:DISPLAY_NAME_MAX_LEN]
    try:
        from memory import config_manager

        config_manager.set_setting(DISPLAY_NAME_SETTING_KEY, clean)
    except Exception:
        pass
    _notify_name(clean)
    return clean


def get_avatar_pixmap(size: int = 64, circular: bool = True):
    """Return a QPixmap of the locked avatar (optionally circular). PyQt lazily imported."""
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QPixmap, QPainter, QPainterPath

    ensure_avatar_asset()
    pix = QPixmap(str(AVATAR_ASSET))
    if pix.isNull():
        return pix
    scaled = pix.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not circular:
        return scaled

    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path)
    # center-crop the scaled image into the circular canvas
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    painter.drawPixmap(0, 0, scaled, x, y, size, size)
    painter.end()
    return out