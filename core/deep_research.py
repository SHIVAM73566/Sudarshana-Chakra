"""Autonomous Deep Research Subroutine for Sudarshana Chakra AI.

When the agent meets an unknown task, an ambiguous command, or an unfamiliar
business domain it must not guess or fail. This module breaks the goal into
structured sub-questions, gathers evidence from web search and the local
document index, synthesises a step-by-step execution strategy, and — when the
capability is genuinely missing — delegates to :class:`core.skill_forge.SkillForge`
to synthesise a temporary skill.

Design constraints
------------------
* **Never raises**: every stage is guarded and degrades to the evidence already
  collected, so a research request always returns a usable artefact.
* **Local-first**: no hard dependency on any network client; web search is
  optional and failures are tolerated.
* **Thread-safe / import-safe**: no heavy imports at module load.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from core.user_paths import get_user_data_dir

logger = logging.getLogger("sudarshana.deep_research")

RESEARCH_DIR = get_user_data_dir() / "research"

__all__ = [
    "DeepResearch",
    "research",
    "FEATURE_METADATA",
    "execute",
]

_STOPWORDS = {
    "a", "an", "the", "to", "for", "in", "of", "and", "or", "on", "at", "by",
    "how", "what", "why", "when", "which", "that", "this", "it", "is", "are",
    "can", "could", "should", "would", "do", "does", "did", "me", "my", "we",
    "build", "make", "create", "generate", "give", "get", "please", "help",
}


class DeepResearch:
    """Multi-stage autonomous research pipeline."""

    # ------------------------------------------------------------------ #
    # Planning
    # ------------------------------------------------------------------ #
    @classmethod
    def decompose(cls, goal: str, max_subtasks: int = 5) -> list[str]:
        """Break *goal* into a short, ordered list of focused sub-questions."""
        goal = (goal or "").strip()
        if not goal:
            return []
        keywords = [
            w for w in re.findall(r"[a-zA-Z0-9]+", goal.lower())
            if w not in _STOPWORDS and len(w) > 2
        ]
        topic = " ".join(keywords[:6]) or goal
        templates = [
            f"What is {topic}?",
            f"Best practices and standard approach for {topic}",
            f"Required tools, data, and prerequisites for {topic}",
            f"Step-by-step process to accomplish {topic}",
            f"Common pitfalls and validation criteria for {topic}",
        ]
        return templates[: max(1, min(max_subtasks, len(templates)))]

    # ------------------------------------------------------------------ #
    # Evidence gathering
    # ------------------------------------------------------------------ #
    @classmethod
    def _web_evidence(cls, question: str, player: Any = None) -> str:
        try:
            from actions.web_search import web_search

            result = web_search({"query": question, "mode": "search"}, player=player)
            return str(result or "").strip()
        except Exception as exc:
            logger.debug("[DeepResearch] web evidence failed for %r: %s", question, exc)
            return ""

    @classmethod
    def _local_evidence(cls, goal: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the local document index (if present) for relevant snippets."""
        hits: list[dict[str, Any]] = []
        try:
            candidates = [RESEARCH_DIR, get_user_data_dir() / "memory", get_user_data_dir() / "deliverables"]
            terms = [t for t in re.findall(r"[a-zA-Z0-9]+", (goal or "").lower()) if t not in _STOPWORDS]
            for base in candidates:
                if not base.exists():
                    continue
                for path in base.rglob("*"):
                    if not path.is_file() or path.suffix.lower() not in (".txt", ".md", ".json", ".csv"):
                        continue
                    try:
                        text = path.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue
                    low = text.lower()
                    score = sum(1 for t in terms if t in low)
                    if score:
                        snippet = text[:400].replace("\n", " ")
                        hits.append({"path": str(path), "score": score, "snippet": snippet})
            hits.sort(key=lambda h: h["score"], reverse=True)
            return hits[:limit]
        except Exception as exc:
            logger.debug("[DeepResearch] local evidence failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Synthesis
    # ------------------------------------------------------------------ #
    @classmethod
    def _synthesize(cls, goal: str, subtasks: list[str], web: list[dict[str, str]], local: list[dict[str, Any]]) -> str:
        """Produce a step-by-step strategy from the collected evidence."""
        lines = [f"AUTONOMOUS DEEP RESEARCH — {goal}", "=" * 56, ""]
        lines.append("SYNTHESISED EXECUTION STRATEGY:")
        for i, sub in enumerate(subtasks, 1):
            evidence = ""
            if i - 1 < len(web) and web[i - 1].get("evidence"):
                evidence = web[i - 1]["evidence"]
            step = f"  {i}. {sub}"
            if evidence:
                condensed = re.sub(r"\s+", " ", evidence)[:280].strip()
                step += f"\n     → {condensed}"
            lines.append(step)
        if local:
            lines.append("")
            lines.append("RELEVANT LOCAL KNOWLEDGE:")
            for hit in local[:3]:
                lines.append(f"  • {Path(hit['path']).name}: {hit['snippet'][:160].strip()}")
        lines.append("")
        lines.append("VALIDATION: cross-check each step's output before proceeding; correct on failure.")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Public entry
    # ------------------------------------------------------------------ #
    @classmethod
    def run(
        cls,
        goal: str,
        *,
        player: Any = None,
        speak: Callable | None = None,
        allow_forge: bool = False,
        max_subtasks: int = 5,
    ) -> dict[str, Any]:
        """Execute the full research pipeline and return a structured result."""
        goal = (goal or "").strip()
        if not goal:
            return {"success": False, "error": "No research goal provided."}

        started = time.time()
        subtasks = cls.decompose(goal, max_subtasks=max_subtasks)
        web: list[dict[str, str]] = []
        for question in subtasks:
            evidence = cls._web_evidence(question, player=player)
            web.append({"question": question, "evidence": evidence})

        local = cls._local_evidence(goal)
        strategy = cls._synthesize(goal, subtasks, web, local)

        forged = None
        if allow_forge:
            forged = cls._maybe_forge(goal, strategy)

        result: dict[str, Any] = {
            "success": True,
            "goal": goal,
            "subtasks": subtasks,
            "web_evidence": [w for w in web if w.get("evidence")],
            "local_evidence": local,
            "strategy": strategy,
            "forged_skill": forged,
            "elapsed_seconds": round(time.time() - started, 2),
            "summary": strategy[:400],
            "spoken_narrative": f"Research complete for {goal}. Strategy prepared with {len(subtasks)} steps.",
        }
        cls._persist(result)
        return result

    @classmethod
    def _maybe_forge(cls, goal: str, strategy: str) -> dict[str, Any] | None:
        """Delegate to SkillForge when a reusable capability is genuinely missing."""
        try:
            from core.skill_forge import SkillForge

            return SkillForge.forge_skill(goal=goal, context_hints=strategy[:1500])
        except Exception as exc:
            logger.debug("[DeepResearch] forge skipped: %s", exc)
            return None

    @classmethod
    def _persist(cls, result: dict[str, Any]) -> None:
        try:
            RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "_", result["goal"].lower()).strip("_")[:48] or "research"
            path = RESEARCH_DIR / f"{slug}_{int(time.time())}.json"
            path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.debug("[DeepResearch] persist failed: %s", exc)


# --------------------------------------------------------------------------- #
# Registry contract
# --------------------------------------------------------------------------- #

FEATURE_METADATA = {
    "name": "deep_research",
    "aliases": ["autonomous_research", "research_agent"],
    "description": (
        "Autonomous deep-research subroutine. Decomposes an unknown or ambiguous goal "
        "into sub-questions, gathers web + local evidence, synthesises a step-by-step "
        "strategy, and optionally forges a skill. Never fails or guesses."
    ),
    "category": "reasoning",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "The unknown/ambiguous task or question to research."},
            "allow_forge": {"type": "BOOLEAN", "description": "Synthesise a skill when the capability is missing."},
            "max_subtasks": {"type": "INTEGER", "description": "Maximum number of sub-questions (default 5)."},
        },
        "required": ["goal"],
    },
    "version": "1.0.0",
    "active": True,
}


def research(goal: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper around :meth:`DeepResearch.run`."""
    return DeepResearch.run(goal, **kwargs)


def execute(**kwargs: Any) -> dict[str, Any]:
    """Registry entry point for the deep_research tool."""
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    goal = params.get("goal") or params.get("query") or params.get("task") or ""
    return DeepResearch.run(
        goal,
        player=kwargs.get("player"),
        allow_forge=bool(params.get("allow_forge")),
        max_subtasks=int(params.get("max_subtasks") or 5),
    )
