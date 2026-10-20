"""Process-wide error boundaries and log redaction.

Installed once at startup so an uncaught exception - raised on the Qt main
thread or inside a bare ``threading.Thread`` - is journaled to a redacted
crash file instead of disappearing into stderr. Every hook is defensive:
an error inside the boundary can never take the app down.

Standard library only; imports no project modules except the pure
``core.security`` redactor.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.security import redact_secrets

__all__ = [
    "crash_dir",
    "install",
    "install_error_boundaries",
    "install_log_redaction",
]

_MAX_CRASH_FILES = 20
_STATE: dict[str, Any] = {"installed": False, "sys": None, "thread": None}


def crash_dir() -> Path:
    """Directory that receives ``crash_<timestamp>_<incident>.log`` files."""
    path = Path(__file__).resolve().parent.parent / "logs"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path


def _prune(directory: Path) -> None:
    try:
        files = sorted(directory.glob("crash_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[_MAX_CRASH_FILES:]:
            try:
                stale.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _write_crash(kind: str, text: str, thread_name: str | None = None) -> str:
    incident = uuid.uuid4().hex[:10].upper()
    directory = crash_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = directory / f"crash_{stamp}_{incident}.log"
    body = redact_secrets(text)
    header = f"kind={kind} incident={incident} time={datetime.now().isoformat(timespec='seconds')}"
    if thread_name:
        header += f" thread={thread_name}"
    try:
        path.write_text(f"{header}\n{body}\n", encoding="utf-8")
        _prune(directory)
    except Exception:
        pass
    return incident


def _report(kind: str, text: str, thread_name: str | None = None) -> None:
    try:
        incident = _write_crash(kind, text, thread_name)
        safe = redact_secrets(text)
        try:
            sys.stderr.write(f"[Sudarshana] {kind} error logged (incident {incident})\n{safe}\n")
            sys.stderr.flush()
        except Exception:
            pass
    except Exception:
        pass


def _sys_hook(exc_type, exc_value, exc_tb) -> None:
    if exc_type is KeyboardInterrupt:
        return
    try:
        raw = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        raw = f"{exc_type!r}: {exc_value!r}"
    _report("uncaught", raw)


def _thread_hook(args) -> None:
    try:
        name = getattr(getattr(args, "thread", None), "name", None)
        raw = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
    except Exception:
        name = None
        raw = "unprintable thread exception"
    if getattr(args, "exc_type", None) is SystemExit:
        return
    _report("uncaught-thread", raw, name)


class _RedactionFilter(logging.Filter):
    """Scrub credentials from log messages before they reach any handler."""

    _sudarshana_redaction = True

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            args = record.args
            if isinstance(args, tuple):
                record.args = tuple(redact_secrets(a) if isinstance(a, str) else a for a in args)
            elif isinstance(args, dict):
                record.args = {
                    key: (redact_secrets(value) if isinstance(value, str) else value)
                    for key, value in args.items()
                }
        except Exception:
            pass
        return True


def install_log_redaction() -> None:
    """Attach the credential redactor to the root logger and its handlers."""
    try:
        filter_ = _RedactionFilter()
        root = logging.getLogger()
        root.addFilter(filter_)
        for handler in root.handlers:
            if not any(getattr(f, "_sudarshana_redaction", False) for f in handler.filters):
                handler.addFilter(filter_)
    except Exception:
        pass


def install_error_boundaries() -> bool:
    """Install the sys/threading exception hooks. Idempotent."""
    if _STATE["installed"]:
        install_log_redaction()
        return True
    try:
        _STATE["sys"] = sys.excepthook
        sys.excepthook = _sys_hook
    except Exception:
        pass
    try:
        _STATE["thread"] = getattr(threading, "excepthook", None)
        threading.excepthook = _thread_hook  # type: ignore[assignment]
    except Exception:
        pass
    _STATE["installed"] = True
    install_log_redaction()
    return True


install = install_error_boundaries
