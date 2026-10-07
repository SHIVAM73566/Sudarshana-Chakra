"""Voice biometric pass-phrase security gate for Sudarshana Chakra.

Provides a deterministic authorization layer in front of voice commands.
A registered user enrols a spoken pass-phrase; while the lock is engaged,
voice input that does not present the voice password is rejected and the
user is asked for it, with a safe text-input fallback.

This is a local, dependency-free gate. It is intentionally conservative:
failures never raise, and a locked state only ever *narrows* what voice can
do (typed/text commands remain available as the fallback channel).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from typing import Optional, Tuple

from core.user_paths import get_user_data_dir

_LOCK = threading.RLock()

AUTH_DENIED_MESSAGE = (
    "Voice authorization is enabled. Please provide the voice password."
)
DEFAULT_USER = "User-1"
SESSION_TTL_SECONDS = 30 * 60

_AUTHORIZED_UNTIL = 0.0

_VOICE_SOURCES = {"mic", "voice", "audio", "mobile", "wake"}

# Listeners are notified whenever the lock state changes so the UI (avatar
# portal, status badges) can reflect it. Signature: fn(locked: bool, denied: bool).
_lock_listeners = []


def register_lock_listener(fn) -> None:
    if callable(fn) and fn not in _lock_listeners:
        _lock_listeners.append(fn)


def _notify_lock(denied: bool = False) -> None:
    try:
        locked = is_locked()
    except Exception:
        locked = False
    for fn in list(_lock_listeners):
        try:
            fn(locked, denied)
        except Exception:
            pass


def _store_path():
    d = get_user_data_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d / "voice_security.json"


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_phrase(phrase: str, salt: str) -> str:
    norm = _normalize(phrase)
    return hashlib.sha256((salt + ":" + norm).encode("utf-8")).hexdigest()


def _default_state() -> dict:
    return {
        "enabled": False,
        "registered_user": DEFAULT_USER,
        "phrase_hash": "",
        "phrase_hint": "",
        "salt": "",
        "master_hash": "",
        "master_salt": "",
        "failed_attempts": 0,
        "last_failed_at": 0.0,
        "updated_at": 0.0,
    }


def _load() -> dict:
    state = _default_state()
    try:
        p = _store_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in state.items():
                    if k in data:
                        state[k] = data[k]
    except Exception:
        pass
    return state


def _save(state: dict) -> None:
    try:
        state["updated_at"] = time.time()
        _store_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _authorize_session() -> None:
    global _AUTHORIZED_UNTIL
    _AUTHORIZED_UNTIL = time.time() + SESSION_TTL_SECONDS


def _session_authorized() -> bool:
    return time.time() < _AUTHORIZED_UNTIL


def is_enabled() -> bool:
    with _LOCK:
        return bool(_load().get("enabled"))


def has_passphrase() -> bool:
    with _LOCK:
        return bool(_load().get("phrase_hash"))


def is_locked() -> bool:
    """True when the voice gate is active (enabled AND enrolled)."""
    with _LOCK:
        s = _load()
        return bool(s.get("enabled")) and bool(s.get("phrase_hash"))


def register_phrase(phrase: str, user: Optional[str] = None, hint: str = "") -> bool:
    """Enrol (or replace) the voice password. Returns True on success."""
    phrase = str(phrase or "").strip()
    if len(_normalize(phrase)) < 3:
        return False
    with _LOCK:
        s = _load()
        s["salt"] = s.get("salt") or _new_salt()
        s["phrase_hash"] = _hash_phrase(phrase, s["salt"])
        if user:
            s["registered_user"] = str(user).strip()[:40] or DEFAULT_USER
        if hint:
            s["phrase_hint"] = str(hint).strip()[:80]
        s["failed_attempts"] = 0
        _save(s)
    return True


def forget_phrase() -> None:
    with _LOCK:
        s = _load()
        s["phrase_hash"] = ""
        s["salt"] = ""
        s["phrase_hint"] = ""
        s["master_hash"] = ""
        s["master_salt"] = ""
        s["enabled"] = False
        s["failed_attempts"] = 0
        _save(s)
    _notify_lock()


def set_enabled(enabled: bool) -> bool:
    """Enable/disable the lock. Enabling requires an enrolled phrase."""
    with _LOCK:
        s = _load()
        if enabled and not s.get("phrase_hash"):
            return False
        s["enabled"] = bool(enabled)
        if not enabled:
            global _AUTHORIZED_UNTIL
            _AUTHORIZED_UNTIL = 0.0
        _save(s)
    _notify_lock()
    return True


def set_master_password(password: str) -> bool:
    """Enrol (or replace) the text master password used as a mic-less fallback."""
    pw = str(password or "").strip()
    if len(pw) < 4:
        return False
    with _LOCK:
        s = _load()
        s["master_salt"] = s.get("master_salt") or _new_salt()
        s["master_hash"] = _hash_phrase(pw, s["master_salt"])
        _save(s)
    return True


def has_master_password() -> bool:
    with _LOCK:
        return bool(_load().get("master_hash"))


def verify_master_password(password: str) -> bool:
    """Authorize the current session using the text master password."""
    with _LOCK:
        s = _load()
        if not s.get("master_hash"):
            return False
        candidate = _hash_phrase(password, s.get("master_salt", ""))
        ok = hmac.compare_digest(s["master_hash"], candidate)
        if ok:
            s["failed_attempts"] = 0
            _authorize_session()
        else:
            s["failed_attempts"] = int(s.get("failed_attempts", 0)) + 1
            s["last_failed_at"] = time.time()
        _save(s)
    if ok:
        _notify_lock()
    return ok


def verify_phrase(phrase: str) -> bool:
    with _LOCK:
        s = _load()
        if not s.get("phrase_hash"):
            return False
        if _session_authorized():
            return True
        expected = s["phrase_hash"]
        candidate = _hash_phrase(phrase, s.get("salt", ""))
        ok = hmac.compare_digest(expected, candidate)
        if ok:
            s["failed_attempts"] = 0
            _authorize_session()
        else:
            s["failed_attempts"] = int(s.get("failed_attempts", 0)) + 1
            s["last_failed_at"] = time.time()
        _save(s)
    if ok:
        _notify_lock()
    return ok


def status() -> dict:
    with _LOCK:
        s = _load()
        return {
            "enabled": bool(s.get("enabled")),
            "enrolled": bool(s.get("phrase_hash")),
            "registered_user": s.get("registered_user", DEFAULT_USER),
            "session_authorized": _session_authorized(),
            "hint": s.get("phrase_hint", ""),
            "has_master_password": bool(s.get("master_hash")),
        }


def _is_voice_source(source: Optional[str]) -> bool:
    return str(source or "").strip().lower() in _VOICE_SOURCES


def _is_lock_command(n: str) -> bool:
    return any(k in n for k in (
        "lock voice", "lock my voice", "lock the voice", "voice lock on",
        "enable voice lock", "enable voice security", "enable voice authorization",
        "lock voice for security", "voice security on", "secure my voice",
    ))


def _is_unlock_command(n: str) -> bool:
    return any(k in n for k in (
        "disable voice lock", "disable voice security", "disable voice authorization",
        "turn off voice security", "voice lock off", "voice security off",
    )) and "password" not in n


def _is_register_command(n: str) -> bool:
    return any(k in n for k in (
        "register voice password", "register my voice", "register voice",
        "set voice password", "set my voice password", "enroll voice",
        "enrol voice", "enroll my voice", "create voice password",
    ))


def _is_forget_command(n: str) -> bool:
    return any(k in n for k in (
        "forget voice password", "remove voice password", "delete voice password",
        "clear voice password", "reset voice password",
    ))


def _is_status_command(n: str) -> bool:
    return any(k in n for k in (
        "voice security status", "voice lock status", "voice status",
        "is voice lock", "voice security report",
    ))


def _is_master_register_command(n: str) -> bool:
    return any(k in n for k in (
        "set voice master password", "set master password", "register master password",
        "create master password", "set text master password", "set my master password",
    ))


def _extract_master_phrase(text: str) -> str:
    raw = " ".join(str(text or "").strip().split())
    low = raw.lower()
    prefixes = (
        "set voice master password", "set text master password", "set my master password",
        "set master password", "register master password", "create master password",
    )
    for p in prefixes:
        if low.startswith(p):
            return raw[len(p):].strip(" :,-").strip()
    return ""


def _matches_master(state: dict, n: str) -> bool:
    if not state.get("master_hash"):
        return False
    candidates = [n]
    for p in ("master password is", "voice master password is", "text master password is",
              "master password", "master password:", "unlock with master password"):
        if n.startswith(p):
            candidates.append(n[len(p):].strip(" :,-").strip())
    for c in candidates:
        if not c:
            continue
        if hmac.compare_digest(state["master_hash"], _hash_phrase(c, state.get("master_salt", ""))):
            return True
    return False


def _extract_register_phrase(text: str) -> str:
    raw = " ".join(str(text or "").strip().split())
    low = raw.lower()
    prefixes = (
        "register voice password", "register my voice password", "register my voice",
        "register voice", "set voice password", "set my voice password",
        "enroll voice password", "enrol voice password", "enroll voice", "enrol voice",
        "enroll my voice", "create voice password",
    )
    for p in prefixes:
        if low.startswith(p):
            return raw[len(p):].strip(" :,-").strip()
    return ""


def _matches_passphrase(state: dict, n: str) -> bool:
    if not state.get("phrase_hash"):
        return False
    candidates = [n]
    for p in ("voice password is", "my voice password is", "voice password",
              "the password is", "password is", "passphrase is"):
        if n.startswith(p):
            candidates.append(n[len(p):].strip())
    for c in candidates:
        if not c:
            continue
        if hmac.compare_digest(state["phrase_hash"], _hash_phrase(c, state.get("salt", ""))):
            return True
    return False


def gate_text(text: str, source: Optional[str] = None) -> Tuple[bool, bool, Optional[str]]:
    """Authorization gate for a single utterance.

    Returns ``(handled, allowed, message)``:
    * ``handled`` True  -> the gate consumed the utterance; caller should stop.
    * ``allowed`` True  -> caller may proceed to normal command handling.
    * ``message``       -> optional line to show / speak to the user.
    """
    try:
        n = _normalize(text)
        if not n:
            return (False, True, None)

        with _LOCK:
            state = _load()

            if _is_status_command(n):
                st = status()
                if not st["enrolled"]:
                    return (True, False, "Voice authorization is not enrolled.")
                if not st["enabled"]:
                    return (True, False, "Voice authorization is disabled.")
                extra = " A text master password is set as fallback." if st.get("has_master_password") else " No text master password is set."
                return (True, False, "Voice authorization is enabled and active for " + st["registered_user"] + "." + extra)

            if _is_forget_command(n):
                forget_phrase()
                return (True, False, "Voice password removed. Voice authorization is now disabled.")

            if _is_master_register_command(n):
                pw = _extract_master_phrase(text)
                if not pw:
                    return (True, False, "Please say 'set master password' followed by your chosen text password.")
                if set_master_password(pw):
                    return (True, False, "Text master password saved. It can unlock voice authorization when the microphone is unavailable.")
                return (True, False, "That master password is too short. Please use at least four characters.")

            if _is_register_command(n):
                phrase = _extract_register_phrase(text)
                if not phrase:
                    return (True, False, "Please say 'register voice password' followed by your chosen phrase.")
                if register_phrase(phrase):
                    set_enabled(True)
                    return (True, False, f"Voice password enrolled for {DEFAULT_USER}. Voice authorization is now enabled.")
                return (True, False, "That voice password is too short. Please use at least three characters.")

            if _is_unlock_command(n):
                if set_enabled(False):
                    return (True, False, "Voice authorization disabled.")
                return (True, False, "Voice authorization is already disabled.")

            if _is_lock_command(n):
                if not state.get("phrase_hash"):
                    return (True, False, "No voice password is enrolled yet. Say 'register voice password' followed by your phrase first.")
                set_enabled(True)
                return (True, False, "Voice authorization is now enabled. Only the registered voice password will be accepted.")

            if state.get("enabled") and state.get("phrase_hash") and (_matches_passphrase(state, n) or _matches_master(state, n)):
                state["failed_attempts"] = 0
                _save(state)
                _authorize_session()
                _notify_lock()
                return (True, False, "Voice authorized. Welcome back.")

            if is_locked() and _is_voice_source(source) and not _session_authorized():
                _notify_lock(denied=True)
                return (True, False, AUTH_DENIED_MESSAGE)

        return (False, True, None)
    except Exception:
        return (False, True, None)