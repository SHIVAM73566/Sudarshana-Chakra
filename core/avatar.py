"""Companion-avatar binding for Sudarshana Chakra.

The avatar is **user-customisable**. A user-selected image is stored in the
per-user data directory and takes priority everywhere the avatar is shown. If no
custom image is set (or it is deleted/corrupt), the app falls back to the
embedded default portrait, which is restored to ``assets/`` on boot so it can
never be permanently broken.

Public API
----------
``get_display_name()`` / ``set_display_name(name)``  - the text label
``get_avatar_pixmap(size, circular)``                - the image (custom or default)
``set_custom_avatar(path)``                          - import a user image
``clear_custom_avatar()``                            - revert to the default portrait
``has_custom_avatar()`` / ``custom_avatar_path()``   - inspect custom state
``ensure_avatar_asset()``                            - restore the default fallback
``register_avatar_listener(fn)``                     - notified when the image changes
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import stat
from pathlib import Path

from core.avatar_asset import AVATAR_BYTES_B64, AVATAR_SHA256

BASE_DIR = Path(__file__).resolve().parent.parent
AVATAR_ASSET = BASE_DIR / "assets" / "sudarshana_avatar_core.png"

# Presented wherever the avatar is pinned.
AVATAR_LABEL = "\U0001F5BC\uFE0F Companion Avatar"
DEFAULT_DISPLAY_NAME = "Guardian Avatar"
DISPLAY_NAME_SETTING_KEY = "avatar_display_name"
DISPLAY_NAME_MAX_LEN = 40

# Supported image extensions for custom avatars.
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
# Animated image formats (rendered as a static first frame inside Qt labels, but
# preserved in full for the web avatar portal).
_ANIMATED_SUFFIXES = {".gif", ".webp", ".apng"}
# 3D / model formats (GLB, GLTF, OBJ, FBX, VRM). These are handed to the web
# avatar portal which renders them with three.js when present.
_MODEL_SUFFIXES = {".glb", ".gltf", ".obj", ".fbx", ".vrm", ".stl", ".ply"}
_MAX_CUSTOM_BYTES = 64 * 1024 * 1024  # 64 MB safety cap (3D models are larger)

# Listeners: name changes and image changes both notify their registries.
_name_listeners: list = []
_avatar_listeners: list = []


def register_name_listener(fn) -> None:
    if callable(fn) and fn not in _name_listeners:
        _name_listeners.append(fn)


def register_avatar_listener(fn) -> None:
    if callable(fn) and fn not in _avatar_listeners:
        _avatar_listeners.append(fn)


def _notify_name(name: str) -> None:
    for fn in list(_name_listeners):
        try:
            fn(name)
        except Exception:
            pass


def _notify_avatar() -> None:
    for fn in list(_avatar_listeners):
        try:
            fn()
        except Exception:
            pass


def _embedded_bytes() -> bytes:
    return base64.b64decode(AVATAR_BYTES_B64)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _user_dir() -> Path:
    try:
        from core.user_paths import get_user_data_dir

        base = get_user_data_dir()
    except Exception:
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "SudarshanaAI"
    target = base / "avatar"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return target


def custom_avatar_path() -> Path:
    """Location of the user-chosen avatar (may not exist)."""
    return _user_dir() / "custom_avatar.png"


def custom_avatar_manifest_path() -> Path:
    """Metadata describing the current custom avatar (kind, source name, model)."""
    return _user_dir() / "custom_avatar.json"


def _write_manifest(data: dict) -> None:
    try:
        import json

        custom_avatar_manifest_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def custom_avatar_manifest() -> dict:
    try:
        import json

        path = custom_avatar_manifest_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def custom_avatar_kind() -> str:
    """Return 'image' | 'animated' | 'model' | 'none' for the current avatar."""
    manifest = custom_avatar_manifest()
    kind = str(manifest.get("kind", "")).strip().lower()
    if kind in ("image", "animated", "model"):
        return kind
    path = custom_avatar_path()
    if path.is_file():
        if path.suffix.lower() in _ANIMATED_SUFFIXES:
            return "animated"
        return "image"
    return "none"



def avatar_asset_matches() -> bool:
    """True if the on-disk default asset exactly matches the embedded original."""
    try:
        return AVATAR_ASSET.is_file() and _sha256(AVATAR_ASSET.read_bytes()) == AVATAR_SHA256
    except Exception:
        return False


def ensure_avatar_asset() -> Path:
    """Restore the *default* avatar asset if missing/altered. Never touches custom."""
    if not avatar_asset_matches():
        data = _embedded_bytes()
        AVATAR_ASSET.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(AVATAR_ASSET, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
        AVATAR_ASSET.write_bytes(data)
    return AVATAR_ASSET


def has_custom_avatar() -> bool:
    """True if a valid user-chosen avatar is present."""
    path = custom_avatar_path()
    try:
        return path.is_file() and path.stat().st_size > 0
    except Exception:
        return False


def effective_avatar_path() -> Path:
    """The image that should actually be displayed (custom if set, else default)."""
    if has_custom_avatar():
        return custom_avatar_path()
    ensure_avatar_asset()
    return AVATAR_ASSET


def set_custom_avatar(source_path: str | os.PathLike[str]) -> tuple[bool, str]:
    """Import ``source_path`` as the new avatar. Returns ``(ok, message)``.

    Accepts still images (PNG/JPG/BMP/WEBP), animated images (GIF/WEBP/APNG) and
    3D models (GLB/GLTF/OBJ/FBX/VRM). Still images are normalised to a 512x512
    PNG via Pillow; animated images keep their first frame as a preview plus the
    full animated file for the web portal; 3D models are stored verbatim and
    rendered by the web avatar portal.
    """
    src = Path(str(source_path))
    if not src.is_file():
        return False, "That file does not exist."
    suffix = src.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES and suffix not in _MODEL_SUFFIXES:
        return False, "Unsupported avatar type. Use PNG, JPG, WEBP, GIF or a 3D model (GLB/GLTF/OBJ/FBX/VRM)."
    try:
        if src.stat().st_size > _MAX_CUSTOM_BYTES:
            return False, "Avatar file is too large (max 64 MB)."
    except Exception:
        pass

    dest = custom_avatar_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    kind = "image"

    # 3D / model path: store verbatim alongside a preview-less manifest.
    if suffix in _MODEL_SUFFIXES:
        model_dest = _user_dir() / f"custom_model{suffix}"
        try:
            shutil.copyfile(src, model_dest)
        except Exception as exc:
            return False, f"Could not save the 3D model: {exc}"
        _write_manifest({"kind": "model", "source": src.name, "model_file": model_dest.name})
        _notify_avatar()
        return True, "3D avatar model saved. It will render in the avatar portal."

    # Animated path: keep the full animated file, plus a PNG preview frame.
    if suffix in _ANIMATED_SUFFIXES:
        animated_dest = _user_dir() / f"custom_animated{suffix}"
        try:
            shutil.copyfile(src, animated_dest)
        except Exception as exc:
            return False, f"Could not save the animated avatar: {exc}"
        preview_path = _user_dir() / "custom_animated_preview.png"
        preview_ok = False
        try:
            from PIL import Image

            with Image.open(src) as img:
                img.seek(0)
                frame = img.convert("RGBA")
                side = min(frame.size)
                left = (frame.width - side) // 2
                top = (frame.height - side) // 2
                frame = frame.crop((left, top, left + side, top + side)).resize((512, 512))
                frame.save(preview_path, format="PNG")
                preview_ok = True
        except Exception:
            preview_ok = False
        if preview_ok:
            try:
                shutil.copyfile(preview_path, dest)
            except Exception:
                pass
        _write_manifest(
            {
                "kind": "animated",
                "source": src.name,
                "animated_file": animated_dest.name,
                "preview_file": preview_path.name if preview_ok else "",
            }
        )
        _notify_avatar()
        return True, "Animated avatar saved."

    # Still image path: normalise to a clean square PNG.
    normalised = False
    try:
        from PIL import Image

        with Image.open(src) as img:
            img = img.convert("RGBA")
            side = min(img.size)
            left = (img.width - side) // 2
            top = (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize((512, 512))
            img.save(dest, format="PNG")
            normalised = True
    except Exception:
        normalised = False

    if not normalised:
        try:
            shutil.copyfile(src, dest)
        except Exception as exc:
            return False, f"Could not save the avatar: {exc}"

    _write_manifest({"kind": "image", "source": src.name})
    _notify_avatar()
    return True, "Avatar updated successfully."


def clear_custom_avatar() -> bool:
    """Delete the custom avatar and revert to the embedded default portrait."""
    removed = False
    for path in (
        custom_avatar_path(),
        custom_avatar_manifest_path(),
    ):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except Exception:
            pass
    for extra in _user_dir().glob("custom_animated*"):
        try:
            extra.unlink()
        except Exception:
            pass
    for extra in _user_dir().glob("custom_model*"):
        try:
            extra.unlink()
        except Exception:
            pass
    _notify_avatar()
    return True if removed else False



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
    """Persist a new display name. Does not affect the avatar image."""
    clean = (str(name or "").strip() or DEFAULT_DISPLAY_NAME)[:DISPLAY_NAME_MAX_LEN]
    try:
        from memory import config_manager

        config_manager.set_setting(DISPLAY_NAME_SETTING_KEY, clean)
    except Exception:
        pass
    _notify_name(clean)
    return clean


def avatar_cache_key() -> str:
    """A value that changes whenever the displayed avatar changes (for UI caching)."""
    path = effective_avatar_path()
    try:
        stat_info = path.stat()
        return f"{path}:{int(stat_info.st_mtime)}:{stat_info.st_size}"
    except Exception:
        return str(path)


def get_avatar_pixmap(size: int = 64, circular: bool = True):
    """Return a QPixmap of the current avatar (custom or default). PyQt lazily imported.

    For 3D-model avatars with no image preview, returns a null pixmap so callers
    can fall back to a logo; the web portal renders the actual 3D model.
    """
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QPixmap, QPainter, QPainterPath

    source = effective_avatar_path()
    if custom_avatar_kind() == "model" and not Path(source).is_file():
        return QPixmap()
    pix = QPixmap(str(source))
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
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    painter.drawPixmap(0, 0, scaled, x, y, size, size)
    painter.end()
    return out
