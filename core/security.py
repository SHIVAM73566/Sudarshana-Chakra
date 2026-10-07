"""Central security hardening utilities for Sudarshana Chakra.

Pure standard-library helpers applied at trust boundaries:

* :func:`redact_secrets`  - scrub credentials before they reach logs/UI/errors.
* :func:`safe_join`       - resolve an untrusted path segment under a base dir,
                            blocking traversal (``..``, absolute paths, NUL).
* :func:`sanitize_prompt` - strip control characters, bound length and
                            neutralize common prompt-injection directives that
                            are routed to downstream LLMs.
* :class:`RateLimiter`    - lightweight in-memory per-client rate limiting for
                            network/API boundaries.
* :func:`obfuscate_error` - produce a generic, incident-tagged client error
                            while logging the real exception locally.

No hard dependency on any framework is required to import this module.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path

logger = logging.getLogger("sudarshana.security")

__all__ = [
    "redact_secrets",
    "safe_join",
    "sanitize_prompt",
    "RateLimiter",
    "obfuscate_error",
    "looks_like_injection",
]

# --------------------------------------------------------------------------- #
# Secret redaction
# --------------------------------------------------------------------------- #

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"nvapi-[0-9A-Za-z_\-]{10,}"),
    re.compile(r"sk-or-[0-9A-Za-z_\-]{10,}"),
    re.compile(r"sk-[0-9A-Za-z]{20,}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
    re.compile(r"ghp_[0-9A-Za-z]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|authorization)\b\s*[:=]\s*['\"]?([^\s'\"]{6,})"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}"),
)


def redact_secrets(text: object) -> str:
    """Return *text* with any recognizable credential replaced by ``***``."""
    try:
        out = str(text)
    except Exception:
        return "<unprintable>"
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("***", out)
    return out


# --------------------------------------------------------------------------- #
# Path traversal protection
# --------------------------------------------------------------------------- #

def safe_join(base, untrusted, *, allow_nested: bool = False) -> Path:
    """Resolve *untrusted* beneath *base*, raising ``ValueError`` on traversal.

    When ``allow_nested`` is false (default) only the final path component is
    used, so ``../../etc/passwd`` resolves to ``<base>/passwd``. When true,
    nested relative paths are permitted but must still stay inside *base*.
    """
    base_resolved = Path(base).resolve()
    raw = str(untrusted)
    if "\x00" in raw:
        raise ValueError("NUL byte in path")
    raw = raw.replace("\\", "/").strip().lstrip("/")
    if not allow_nested:
        raw = raw.split("/")[-1]
    if raw in ("", ".", ".."):
        raise ValueError("invalid path segment")

    target = (base_resolved / raw).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError("path traversal blocked") from exc
    if not allow_nested and target.name != raw.split("/")[-1]:
        raise ValueError("path traversal blocked")
    return target


# --------------------------------------------------------------------------- #
# Prompt-injection sanitization
# --------------------------------------------------------------------------- #

_INJECTION_PATTERNS = (
    re.compile(r"(?is)\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|messages?)"),
    re.compile(r"(?i)\bdisregard\b.{0,40}\b(instructions?|rules|prompt)\b"),
    re.compile(r"(?i)\b(you are now|from now on you are|act as)\b\s+(a|an|my)?\s*"),
    re.compile(r"(?i)\b(reveal|print|show|repeat|dump|output)\b.{0,20}\b(system prompt|system message|instructions|api[ _-]?key|secret|password)\b"),
    re.compile(r"(?is)<\s*/?\s*(system|assistant|tool)\b"),
    re.compile(r"(?i)\bnew (system )?instructions?\s*:"),
    re.compile(r"(?i)\boverride\s+(the\s+)?(system|safety|security)\b"),
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def looks_like_injection(text: str) -> bool:
    """True if *text* matches a known prompt-injection heuristic."""
    try:
        return any(p.search(str(text)) for p in _INJECTION_PATTERNS)
    except Exception:
        return False


def sanitize_prompt(text: object, *, max_len: int = 32_768, neutralize: bool = True) -> str:
    """Sanitize untrusted text before it is sent to a downstream LLM.

    * removes NUL/control characters,
    * enforces a hard length cap,
    * optionally neutralizes common injection directives (replaced with a
      bracketed marker so the intent is preserved but not executed).
    """
    if text is None:
        return ""
    value = str(text)
    value = value.replace("\x00", "")
    value = "".join(ch for ch in value if ch == "\n" or ch == "\t" or ch >= " ")
    if neutralize:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(value):
                value = pattern.sub("[filtered: injection attempt]", value)
    value = value[:max_len]
    return value


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #

class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by an arbitrary identifier."""

    def __init__(self, max_events: int = 120, window_seconds: float = 60.0):
        self.max_events = max(1, int(max_events))
        self.window = float(window_seconds)
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events.setdefault(str(key), deque())
            cutoff = now - self.window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True


# --------------------------------------------------------------------------- #
# Error obfuscation
# --------------------------------------------------------------------------- #

def obfuscate_error(exc: BaseException, *, context: str = "") -> dict:
    """Log the real exception locally and return a generic, incident-tagged payload."""
    incident = uuid.uuid4().hex[:12].upper()
    logger.error(
        "Unhandled error [incident %s]%s: %s",
        incident,
        f" in {context}" if context else "",
        redact_secrets(exc),
        exc_info=True,
    )
    return {
        "ok": False,
        "error": "An internal error occurred. Please try again.",
        "incident": incident,
    }