"""
ForgeMemory — the durable failure/success journal behind SkillForge.

SkillForge previously discarded every failure (broken code, Crucible telemetry,
repair history) so the same goal re-forged identically forever. This store keeps
that history on disk and converts recurring failure patterns into lessons that are
injected back into the synthesizer and repair prompts, closing the learning loop.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from core.user_paths import get_user_data_dir

MEMORY_PATH = get_user_data_dir() / "config" / "forge_memory.json"

MAX_FAILURES = 200
MAX_SUCCESSES = 200
MAX_RUNTIME_ERRORS = 150
MAX_LESSONS = 60

STAGE_LABELS = {
    "synthesis": "LLM skill synthesis",
    "ast": "AST validation",
    "dependencies": "dependency resolution",
    "sandbox": "crucible sandbox tests",
    "commit": "saving/registering the skill",
    "runtime": "first live execution",
}


def _empty() -> dict:
    return {"failures": [], "successes": [], "runtime_errors": [], "lessons": []}


def load() -> dict:
    try:
        if MEMORY_PATH.exists():
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty()
                for key in base:
                    value = data.get(key)
                    if isinstance(value, list):
                        base[key] = value
                return base
    except Exception as exc:
        print(f"[ForgeMemory] read failed: {exc}")
    return _empty()


def save(data: dict) -> bool:
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MEMORY_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(MEMORY_PATH)
        return True
    except Exception as exc:
        print(f"[ForgeMemory] write failed: {exc}")
        return False


def _shorten(text: Any, limit: int = 400) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def _error_signature(stage: str, error: str) -> str:
    text = _shorten(error, 300).lower()
    text = re.sub(r"line \d+", "line N", text)
    text = re.sub(r"\b\d+\b", "N", text)
    text = re.sub(r"[^a-z ]", " ", text)
    words = [w for w in text.split() if len(w) > 2][:8]
    return f"{stage}::{' '.join(words)}"


def record_failure(
    goal: str,
    stage: str,
    error: str,
    attempts: int = 0,
    skill_name: str = "",
    code: str = "",
    telemetry: Any = None,
) -> str:
    """Persist a forge failure and promote it to a lesson if the pattern repeats."""
    data = load()
    stage = str(stage or "unknown").lower()
    entry = {
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "goal": _shorten(goal, 300),
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "error": _shorten(error, 800),
        "attempts": int(attempts or 0),
        "skill_name": skill_name or "",
        "signature": _error_signature(stage, error),
        "code_excerpt": _shorten(code, 1200) if code else "",
        "telemetry": telemetry if isinstance(telemetry, (dict, list, str, int, float)) else None,
    }
    data["failures"].append(entry)
    if len(data["failures"]) > MAX_FAILURES:
        data["failures"] = data["failures"][-MAX_FAILURES:]

    signature = entry["signature"]
    prior = sum(1 for f in data["failures"] if f.get("signature") == signature)
    if prior >= 2:
        _promote_lesson(
            data,
            key=signature,
            text=(
                f"Avoid repeating: {entry['stage_label']} failed {prior} times for goals like "
                f"'{entry['goal']}'. Reason: {entry['error']}"
            ),
        )
    save(data)
    return entry["id"]


def record_success(goal: str, skill_name: str, attempts: int = 0) -> None:
    data = load()
    data["successes"].append({
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "goal": _shorten(goal, 300),
        "skill_name": skill_name or "",
        "attempts": int(attempts or 0),
    })
    if len(data["successes"]) > MAX_SUCCESSES:
        data["successes"] = data["successes"][-MAX_SUCCESSES:]
    save(data)


def record_runtime_error(skill_name: str, error: str) -> None:
    """Called when a forged/registered skill raises during real execution."""
    data = load()
    data["runtime_errors"].append({
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "skill_name": str(skill_name or ""),
        "error": _shorten(error, 800),
        "signature": _error_signature("runtime", f"{skill_name} {error}"),
    })
    if len(data["runtime_errors"]) > MAX_RUNTIME_ERRORS:
        data["runtime_errors"] = data["runtime_errors"][-MAX_RUNTIME_ERRORS:]

    signature = _error_signature("runtime", f"{skill_name} {error}")
    prior = sum(1 for r in data["runtime_errors"] if r.get("signature") == signature)
    if prior >= 2:
        _promote_lesson(
            data,
            key=signature,
            text=(
                f"Skill '{skill_name}' crashed {prior} times: {data['runtime_errors'][-1]['error']}. "
                "Guard against this failure mode (empty inputs, missing network, bad formats)."
            ),
        )
    save(data)


def _promote_lesson(data: dict, key: str, text: str) -> None:
    lessons = data.setdefault("lessons", [])
    for lesson in lessons:
        if lesson.get("key") == key:
            lesson["count"] = int(lesson.get("count", 1)) + 1
            lesson["ts"] = time.time()
            lesson["text"] = text
            return
    lessons.append({"key": key, "text": text, "count": 1, "ts": time.time()})
    if len(lessons) > MAX_LESSONS:
        lessons.sort(key=lambda l: (l.get("count", 1), l.get("ts", 0)), reverse=True)
        data["lessons"] = lessons[:MAX_LESSONS]


def add_lesson(text: str, key: str = "") -> None:
    data = load()
    _promote_lesson(data, key or _shorten(text, 80).lower(), _shorten(text, 600))
    save(data)


def lessons_for(goal: str, limit: int = 6) -> str:
    """Returns a prompt block of hard-won lessons relevant to this goal."""
    data = load()
    terms = {t for t in re.split(r"\W+", (goal or "").lower()) if len(t) > 3}
    lessons = data.get("lessons") or []
    if not lessons:
        return ""

    def score(lesson: dict) -> int:
        hay = str(lesson.get("text", "")).lower()
        return sum(1 for t in terms if t in hay) + int(lesson.get("count", 1))

    ranked = sorted(lessons, key=score, reverse=True)[:limit]
    if not ranked:
        return ""

    lines = ["LESSONS FROM PREVIOUS FAILED ATTEMPTS (do not repeat these mistakes):"]
    for i, lesson in enumerate(ranked, 1):
        lines.append(f"{i}. {lesson.get('text', '').strip()}")
    return "\n".join(lines)


def failure_digest(goal: str, limit: int = 4) -> str:
    """Prior failures for this exact goal, used to give the repair loop memory."""
    data = load()
    text = (goal or "").strip().lower()
    matches = [f for f in (data.get("failures") or []) if text and text in str(f.get("goal", "")).lower()]
    if not matches:
        matches = list(data.get("failures") or [])[-limit:]
    matches = matches[-limit:]
    if not matches:
        return ""
    lines = ["THIS CAPABILITY HAS FAILED BEFORE — use a different approach:"]
    for f in matches:
        lines.append(f"- [{f.get('stage_label')}] {f.get('error', '')}")
    return "\n".join(lines)


def stats() -> dict:
    data = load()
    last_success = (data.get("successes") or [{}])[-1]
    return {
        "failures": len(data.get("failures") or []),
        "successes": len(data.get("successes") or []),
        "runtime_errors": len(data.get("runtime_errors") or []),
        "lessons": len(data.get("lessons") or []),
        "last_success_goal": last_success.get("goal", ""),
        "last_success_skill": last_success.get("skill_name", ""),
    }


def recent_failures(limit: int = 8) -> list[dict]:
    return list(reversed(load().get("failures") or []))[:limit]


def clear() -> int:
    data = load()
    count = sum(len(data.get(k) or []) for k in data)
    save(_empty())
    return count
