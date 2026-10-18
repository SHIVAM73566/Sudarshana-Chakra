"""
Self-Improvement Engine (facade over core/skill_forge.py + core/skill_crucible.py)
=================================================================================

Turns "the app threw a traceback" into "the source was repaired and re-verified".
It owns no synthesis or sandboxing logic - those live in ``SkillForge`` and
``SkillCrucible``. This module adds the missing orchestration:

1. **Intercept** - parse a traceback into the failing file, line and error.
2. **Repair**   - hand the broken source to ``SkillForge._repair_code`` with a
                  cumulative error history so consecutive attempts change strategy.
3. **Verify**   - reject unparsable output with ``SkillCrucible.validate_ast``,
                  then compile/pytest the file in place.
4. **Roll back** - if repair never lands, the original bytes are restored.

Only files inside the repository are eligible; every attempt is journaled to
``<user_data>/config/self_improvement.jsonl`` and reported to ForgeMemory.
"""

from __future__ import annotations

import json
import py_compile
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.user_paths import get_user_data_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_PATH = get_user_data_dir() / "config" / "self_improvement.jsonl"
BACKUP_DIR = get_user_data_dir() / "config" / "self_improvement_backups"
TESTS_DIR = REPO_ROOT / "tests"

_FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)')
_ERROR_RE = re.compile(r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt|Exit|Fault))(?::\s*(?P<msg>.*))?$")

__all__ = [
    "parse_traceback",
    "verify_file",
    "heal_file",
    "heal_traceback",
    "install_interceptor",
    "remove_interceptor",
    "journal",
    "SelfHealer",
]


# ----------------------------------------------------------------------------
# traceback interception
# ----------------------------------------------------------------------------
def parse_traceback(text: str) -> Dict[str, Any]:
    """Extracts frames, the failing file/line and the exception from raw output."""
    frames: List[Dict[str, Any]] = []
    for match in _FRAME_RE.finditer(text or ""):
        frames.append(
            {
                "file": match.group("file"),
                "line": int(match.group("line")),
                "function": match.group("func").strip(),
            }
        )

    error_type = ""
    error_message = ""
    for raw_line in reversed((text or "").splitlines()):
        line = raw_line.strip()
        if not line or line.startswith("Traceback") or line.startswith("File "):
            continue
        match = _ERROR_RE.match(line)
        if match:
            error_type = match.group("type")
            error_message = (match.group("msg") or "").strip()
            break

    failing = next(
        (frame for frame in reversed(frames) if "site-packages" not in frame["file"]),
        frames[-1] if frames else None,
    )

    return {
        "frames": frames,
        "error_type": error_type,
        "error_message": error_message,
        "file": (failing or {}).get("file", ""),
        "line": (failing or {}).get("line", 0),
        "function": (failing or {}).get("function", ""),
    }


def journal(entry: Dict[str, Any]) -> None:
    """Appends one attempt record to the JSONL journal (never raises)."""
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = dict(entry)
        record.setdefault("when", time.time())
        with open(JOURNAL_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _forge_memory():
    try:
        from core import forge_memory as ForgeMemory

        return ForgeMemory
    except Exception:
        return None


# ----------------------------------------------------------------------------
# verification
# ----------------------------------------------------------------------------
def _related_tests(target: Path) -> Optional[Path]:
    stem = target.stem
    candidates = [
        TESTS_DIR / f"test_{stem}.py",
        TESTS_DIR / f"test_{stem.replace('-', '_')}.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if TESTS_DIR.is_dir():
        for candidate in sorted(TESTS_DIR.glob("test_*.py")):
            try:
                if stem in candidate.read_text(encoding="utf-8", errors="replace"):
                    return candidate
            except Exception:
                continue
    return None


def verify_file(path: str, run_tests: bool = True, timeout: float = 300.0) -> Tuple[bool, str]:
    """Compiles ``path`` and, when a related test exists, runs it. Returns (ok, output)."""
    target = Path(path)
    if not target.exists():
        return False, f"File not found: {target}"
    try:
        py_compile.compile(str(target), doraise=True)
    except py_compile.PyCompileError as exc:
        return False, f"SyntaxError: {exc}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if not run_tests:
        return True, "Compiled cleanly."

    test_file = _related_tests(target)
    if test_file is None:
        return True, "Compiled cleanly (no related test discovered)."

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {timeout}s: {test_file.name}"
    except Exception as exc:
        return True, f"Compiled cleanly (could not run tests: {type(exc).__name__}: {exc})."

    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return True, f"Compiled and passed {test_file.name}.\n{output[-1200:]}"
    return False, f"Tests failed ({test_file.name}, exit={proc.returncode}):\n{output[-4000:]}"


def _extract_error(output: str) -> str:
    lines = [line.strip() for line in (output or "").splitlines()]
    for line in lines:
        if line.startswith("E ") or line.startswith("E\t") or line.startswith("E   "):
            return line[:600]
    for line in reversed(lines):
        if _ERROR_RE.match(line):
            return line[:600]
    return (lines[-1] if lines else "unknown error")[:600]


# ----------------------------------------------------------------------------
# healing
# ----------------------------------------------------------------------------
def _eligible(target: Path) -> Tuple[bool, str]:
    try:
        resolved = target.resolve()
    except Exception:
        return False, f"Unresolvable path: {target}"
    if not resolved.exists():
        return False, f"File not found: {resolved}"
    if resolved.suffix != ".py":
        return False, f"Refusing to self-heal non-Python file: {resolved.name}"
    if REPO_ROOT not in resolved.parents and resolved.parent != REPO_ROOT:
        return False, f"Refusing to self-heal a file outside the repository: {resolved}"
    return True, ""


def heal_file(
    path: str,
    goal: str = "",
    max_attempts: int = 4,
    apply: bool = True,
    run_tests: bool = True,
    player: Any = None,
) -> Dict[str, Any]:
    """Repairs a single source file until it compiles (and its test passes).

    Returns a report: ``{success, file, attempts, error, output, applied, backup}``.
    """
    target = Path(path)
    ok, reason = _eligible(target)
    if not ok:
        return {"success": False, "file": str(path), "attempts": 0, "error": reason, "output": reason}

    def log(message: str) -> None:
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(message)
            except Exception:
                pass

    original = target.read_text(encoding="utf-8", errors="replace")
    verified, output = verify_file(str(target), run_tests=run_tests)
    if verified:
        journal({"file": str(target), "success": True, "attempts": 0, "note": "already healthy"})
        return {
            "success": True,
            "file": str(target),
            "attempts": 0,
            "error": "",
            "output": output,
            "applied": False,
            "backup": "",
        }

    from core.skill_forge import SkillForge
    from core.skill_crucible import SkillCrucible

    effective_goal = goal or f"Repair {target.name} so it compiles and its tests pass."
    history: List[str] = []
    current = original
    last_error = _extract_error(output)
    backup_path = ""

    for attempt in range(1, max_attempts + 1):
        log(f"🛠️ [SelfHeal] attempt {attempt}/{max_attempts} for {target.name}: {last_error[:120]}")
        repair = SkillForge._repair_code(current, last_error, effective_goal, history)
        if not repair.get("success") or not repair.get("code"):
            history.append(last_error)
            last_error = str(repair.get("error") or "repair model returned no code")
            continue

        candidate = str(repair["code"])
        ast_ok, ast_error = SkillCrucible.validate_ast(candidate)
        if not ast_ok:
            history.append(f"AST rejected repair: {ast_error}")
            last_error = f"AST rejected repair: {ast_error}"
            continue

        if apply:
            if not backup_path:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                backup_target = BACKUP_DIR / f"{target.name}.{int(time.time())}.bak"
                backup_target.write_text(original, encoding="utf-8")
                backup_path = str(backup_target)
            try:
                target.write_text(candidate, encoding="utf-8")
            except Exception as exc:
                last_error = f"Could not write repair: {type(exc).__name__}: {exc}"
                history.append(last_error)
                continue

        current = candidate
        verified, output = verify_file(str(target), run_tests=run_tests)
        if verified:
            journal(
                {
                    "file": str(target),
                    "success": True,
                    "attempts": attempt,
                    "goal": effective_goal,
                    "backup": backup_path,
                }
            )
            memory = _forge_memory()
            if memory is not None:
                try:
                    memory.record_success(goal=effective_goal, skill_name=target.stem, attempts=attempt)
                except Exception:
                    pass
            log(f"✅ [SelfHeal] {target.name} repaired on attempt {attempt}.")
            return {
                "success": True,
                "file": str(target),
                "attempts": attempt,
                "error": "",
                "output": output,
                "applied": bool(apply),
                "backup": backup_path,
            }

        last_error = _extract_error(output)
        history.append(last_error)

    if apply and backup_path:
        try:
            target.write_text(original, encoding="utf-8")
        except Exception:
            pass

    journal(
        {
            "file": str(target),
            "success": False,
            "attempts": max_attempts,
            "goal": effective_goal,
            "error": last_error,
            "restored": bool(apply and backup_path),
        }
    )
    log(f"❌ [SelfHeal] {target.name} could not be repaired automatically: {last_error[:160]}")
    return {
        "success": False,
        "file": str(target),
        "attempts": max_attempts,
        "error": last_error,
        "output": output,
        "applied": bool(apply),
        "backup": backup_path,
        "restored": bool(apply and backup_path),
    }


def heal_traceback(raw_output: str, apply: bool = True, max_attempts: int = 4, player: Any = None) -> Dict[str, Any]:
    """Parses a traceback and heals the file that raised it."""
    parsed = parse_traceback(raw_output)
    if not parsed.get("file"):
        return {
            "success": False,
            "attempts": 0,
            "error": "No Python frame found in the supplied traceback.",
            "parsed": parsed,
        }
    report = heal_file(
        parsed["file"],
        goal=f"Fix {parsed.get('error_type') or 'error'} at line {parsed.get('line')} of {Path(parsed['file']).name}.",
        max_attempts=max_attempts,
        apply=apply,
        player=player,
    )
    report["parsed"] = parsed
    return report


# ----------------------------------------------------------------------------
# global interceptor
# ----------------------------------------------------------------------------
_ORIGINAL_HOOK = None


def install_interceptor(heal: bool = False, player: Any = None) -> bool:
    """Installs a ``sys.excepthook`` that journals every uncaught traceback.

    ``heal=True`` additionally attempts an autonomous repair. Returns True when
    the hook is (now) installed.
    """
    global _ORIGINAL_HOOK
    if _ORIGINAL_HOOK is not None:
        return True

    import traceback as _traceback

    _ORIGINAL_HOOK = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            raw = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
            parsed = parse_traceback(raw)
            journal({"intercepted": True, "error_type": parsed["error_type"], "file": parsed["file"], "line": parsed["line"]})
            if heal and parsed.get("file"):
                heal_file(parsed["file"], apply=True, player=player)
        except Exception:
            pass
        return _ORIGINAL_HOOK(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    return True


def remove_interceptor() -> bool:
    """Restores the original excepthook."""
    global _ORIGINAL_HOOK
    if _ORIGINAL_HOOK is None:
        return False
    sys.excepthook = _ORIGINAL_HOOK
    _ORIGINAL_HOOK = None
    return True


class SelfHealer:
    """Thin object facade so callers can hold a configured healer instance."""

    def __init__(self, apply: bool = True, max_attempts: int = 4, player: Any = None):
        self.apply = apply
        self.max_attempts = max_attempts
        self.player = player

    def heal(self, path: str, goal: str = "") -> Dict[str, Any]:
        return heal_file(
            path,
            goal=goal,
            max_attempts=self.max_attempts,
            apply=self.apply,
            player=self.player,
        )

    def heal_traceback(self, raw_output: str) -> Dict[str, Any]:
        return heal_traceback(
            raw_output,
            apply=self.apply,
            max_attempts=self.max_attempts,
            player=self.player,
        )

    def install(self, heal: bool = False) -> bool:
        return install_interceptor(heal=heal, player=self.player)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sudarshana self-improvement engine")
    parser.add_argument("path", nargs="?", help="file to verify/repair")
    parser.add_argument("--traceback", help="path to a file containing a raw traceback")
    parser.add_argument("--apply", action="store_true", help="write repairs back to disk")
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    if args.traceback:
        text = Path(args.traceback).read_text(encoding="utf-8", errors="replace")
        report = heal_traceback(text, apply=args.apply, max_attempts=args.max_attempts)
    elif args.path:
        report = heal_file(args.path, max_attempts=args.max_attempts, apply=args.apply)
    else:
        print(json.dumps({"journal": str(JOURNAL_PATH), "repo_root": str(REPO_ROOT)}, indent=2))
        return 0

    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
