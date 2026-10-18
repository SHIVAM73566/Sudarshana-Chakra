"""
Sudarshana Chakra Pre-Flight Validation Suite
=============================================

The zero-error gate that must pass before anything is deployed.

Checks (all of them run, failures are aggregated):

1.  SYNTAX      - byte-compile every Python file in the repository.
2.  STATIC      - undefined-name / structural scan (pyflakes when installed).
3.  IMPORTS     - import every module in an isolated subprocess so import-time
                  crashes (missing deps, bad module-level code) are caught.
4.  SCHEMA      - every registered skill must expose a valid Gemini function
                  schema (``{"type": "OBJECT", "properties": {...}}``).
5.  HYGIENE     - rejects bare ``except:`` handlers that swallow
                  ``KeyboardInterrupt`` / ``SystemExit``.
6.  TESTS       - project unit test suite (pytest).

Verification only runs by default. Deployment to git is opt-in via ``--deploy``
so an accidental invocation can never push to a remote.

Usage:
    python core/auto_deploy.py                     # verify only
    python core/auto_deploy.py --json report.json  # verify + write report
    python core/auto_deploy.py --deploy -m "msg"   # verify, stage, commit, push
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures as futures
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "node_modules", "build", "dist",
    "generated", "installer", "scratch", ".pytest_cache", ".playwright-mcp",
    ".idea", ".gradle",
}

DEFAULT_BRANCH = "main"
DEFAULT_REMOTE = "origin"

IMPORT_SNIPPET = (
    "import os, sys, importlib, traceback\n"
    "root = sys.argv[1]\n"
    "os.chdir(root)\n"
    "sys.path.insert(0, root)\n"
    "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
    "target = sys.argv[2][:-3].replace('/', '.').replace('\\\\', '.')\n"
    "try:\n"
    "    importlib.import_module(target)\n"
    "    print('OK')\n"
    "except BaseException as exc:\n"
    "    print('ERRTYPE:' + type(exc).__name__)\n"
    "    print(traceback.format_exc()[-1200:])\n"
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    findings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "findings": self.findings[:200],
            "finding_count": len(self.findings),
        }


def _iter_python_files() -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
    return sorted(files)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def check_syntax(files: Sequence[Path]) -> Check:
    findings: List[str] = []
    for path in files:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True, errors="replace",
        )
        if result.returncode != 0:
            findings.append(f"{_rel(path)}: {(result.stderr or '').strip()[:300]}")
    return Check("syntax", not findings, f"{len(files)} files compiled", findings)


def check_static(files: Sequence[Path]) -> Check:
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        return Check("static", True, "pyflakes not installed - skipped", [])

    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *[str(f) for f in files]],
        capture_output=True, text=True, errors="replace",
    )
    hard = [
        line for line in (result.stdout or "").splitlines()
        if "undefined name" in line or "syntax" in line.lower()
    ]
    soft = (result.stdout or "").splitlines()
    detail = f"{len(soft)} notes, {len(hard)} blocking"
    return Check("static", not hard, detail, hard)


def check_imports(files: Sequence[Path], timeout: int = 90, workers: int = 6) -> Check:
    targets = [f for f in files if f.name not in {"conftest.py", "skill.py", "setup.py"}]
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"

    def probe(path: Path) -> Tuple[str, bool, str]:
        try:
            result = subprocess.run(
                [sys.executable, "-c", IMPORT_SNIPPET, str(PROJECT_ROOT), _rel(path)],
                capture_output=True, text=True, timeout=timeout, env=env, errors="replace",
            )
        except subprocess.TimeoutExpired:
            return _rel(path), False, f"timed out after {timeout}s"
        output = (result.stdout or "") + (result.stderr or "")
        if output.strip().startswith("OK"):
            return _rel(path), True, ""
        return _rel(path), False, output.strip()[-600:]

    findings: List[str] = []
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for name, ok, error in pool.map(probe, targets):
            if not ok:
                findings.append(f"{name}: {error}")
    return Check("imports", not findings, f"{len(targets)} modules imported", findings)


def check_schema() -> Check:
    sys.path.insert(0, str(PROJECT_ROOT))
    env_backup = os.environ.get("QT_QPA_PLATFORM")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    findings: List[str] = []
    try:
        from core.dynamic_registry import DynamicToolRegistry

        DynamicToolRegistry.initialize()
        declarations = DynamicToolRegistry.get_tool_declarations()
        for declaration in declarations:
            schema = declaration.get("parameters")
            name = declaration.get("name", "?")
            if not isinstance(schema, dict):
                findings.append(f"{name}: parameters is not an object")
                continue
            if str(schema.get("type", "")).upper() != "OBJECT":
                findings.append(f"{name}: parameters.type must be OBJECT")
            if not isinstance(schema.get("properties"), dict):
                findings.append(f"{name}: parameters.properties must be an object")
        try:
            json.dumps({"tools": [{"function_declarations": declarations}]})
        except (TypeError, ValueError) as exc:
            findings.append(f"declaration payload is not JSON serializable: {exc}")
        detail = f"{len(declarations)} declarations validated"
    except Exception as exc:  # pragma: no cover - environment dependent
        findings.append(f"{type(exc).__name__}: {exc}")
        detail = "registry unavailable"
    finally:
        if env_backup is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
    return Check("schema", not findings, detail, findings)


def check_hygiene(files: Sequence[Path]) -> Check:
    findings: List[str] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(f"{_rel(path)}:{node.lineno}: bare 'except:' swallows KeyboardInterrupt/SystemExit")
    return Check("hygiene", not findings, "no bare except handlers", findings)


def check_tests(timeout: int = 900) -> Check:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=timeout, errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    summary = ""
    for line in reversed(output.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
            break
    findings: List[str] = []
    if result.returncode != 0:
        findings = [line for line in output.splitlines() if line.startswith(("FAILED", "ERROR"))][:50]
        if not findings:
            findings = output.strip().splitlines()[-25:]
    return Check("tests", result.returncode == 0, summary or f"exit={result.returncode}", findings)


def run_checks(verbose: bool = True) -> Tuple[List[Check], bool]:
    started = time.time()
    files = _iter_python_files()
    if verbose:
        print(f"[preflight] scanning {len(files)} python files under {PROJECT_ROOT}")

    checks: List[Check] = []
    plan = [
        ("syntax", lambda: check_syntax(files)),
        ("static", lambda: check_static(files)),
        ("imports", lambda: check_imports(files)),
        ("schema", check_schema),
        ("hygiene", lambda: check_hygiene(files)),
        ("tests", check_tests),
    ]
    for name, runner in plan:
        try:
            check = runner()
        except Exception as exc:  # pragma: no cover - defensive
            check = Check(name, False, f"check crashed: {type(exc).__name__}: {exc}", [])
        checks.append(check)
        if verbose:
            status = "PASS" if check.passed else "FAIL"
            print(f"[preflight] {status}  {name:<8} {check.detail}")
            for finding in check.findings[:15]:
                print(f"            - {finding[:200]}")

    ok = all(check.passed for check in checks)
    if verbose:
        print(f"[preflight] finished in {time.time() - started:.1f}s -> "
              f"{'0 ERRORS' if ok else 'FAILURES PRESENT'}")
    return checks, ok


def _git(args: Sequence[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(PROJECT_ROOT), text=True,
                          capture_output=True, errors="replace", check=check)


def deploy(commit_message: str, branch: str, remote: str, verbose: bool = True) -> bool:
    status = _git(["status", "--porcelain"]).stdout.strip()
    if not status:
        if verbose:
            print("[deploy] working tree clean - nothing to commit")
        return True

    if verbose:
        print("[deploy] staging changes ...")
    _git(["add", "-A"])

    staged = _git(["diff", "--cached", "--name-only"]).stdout.splitlines()
    forbidden = [name for name in staged if name.endswith((".env", ".key", ".pem"))
                 or "credential" in name.lower() or "api_keys" in name.lower()]
    if forbidden:
        if verbose:
            print(f"[deploy] ABORTED - sensitive files staged: {forbidden}")
        _git(["reset"], check=False)
        return False

    commit = _git(["commit", "-m", commit_message], check=False)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        if verbose:
            print(f"[deploy] commit failed: {(commit.stdout + commit.stderr).strip()[:400]}")
        return False

    push = _git(["push", remote, branch], check=False)
    if push.returncode != 0:
        if verbose:
            print(f"[deploy] push failed: {(push.stdout + push.stderr).strip()[:400]}")
        return False

    if verbose:
        print(f"[deploy] pushed {len(staged)} files to {remote}/{branch}")
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sudarshana Chakra pre-flight validation suite")
    parser.add_argument("--deploy", action="store_true",
                        help="stage, commit and push once every check passes")
    parser.add_argument("-m", "--message", default="chore: verified zero-error build",
                        help="commit message used with --deploy")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--json", dest="json_report", default=None,
                        help="write a JSON report to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    checks, ok = run_checks(verbose=not args.quiet)

    if args.json_report:
        report_path = Path(args.json_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"ok": ok, "checks": [c.as_dict() for c in checks]}, indent=2),
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"[preflight] report written to {args.json_report}")

    if not ok:
        print("[preflight] refusing to deploy: resolve the failures above", file=sys.stderr)
        return 1

    if args.deploy:
        if not deploy(args.message, args.branch, args.remote, verbose=not args.quiet):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
