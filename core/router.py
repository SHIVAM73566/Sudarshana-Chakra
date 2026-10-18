"""
Intent Router (facade over agent/planner.py + agent/executor.py)
===============================================================

Single entrypoint that decides *how* a natural-language goal should be served,
then delegates to the engines that already own that behaviour. This module adds
no execution logic of its own - it classifies, picks the cheapest correct
engine, and normalises the result into one envelope so callers (UI, tools,
services) don't have to know which subsystem handled the request.

Routes
------
``evolution``    the goal asks for a capability that does not exist yet
                 -> ``core.skill_discovery.SkillDiscovery.execute_forge``
``single_tool``  the plan collapses to one tool call
                 -> ``agent.executor._call_tool`` (no DAG overhead)
``dag``          multi-step goal
                 -> ``agent.executor.AgentExecutor.execute`` (plan -> replan loop)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "route",
    "classify",
    "run_plan",
    "create_plan",
    "replan",
    "RouterResult",
]


def create_plan(goal: str, context: str = "") -> Dict[str, Any]:
    """Re-exports the planner so router consumers need a single import."""
    from agent.planner import create_plan as _create_plan

    return _create_plan(goal, context)


def replan(
    goal: str,
    completed_steps: List[Dict[str, Any]],
    failed_step: Dict[str, Any],
    error: str,
) -> Dict[str, Any]:
    """Re-exports planner.replan for the same reason."""
    from agent.planner import replan as _replan

    return _replan(goal, completed_steps, failed_step, error)


def _evolution_request(goal: str) -> Optional[Dict[str, str]]:
    """Delegates forge-trigger detection to the existing SkillDiscovery rules."""
    try:
        from core.skill_discovery import SkillDiscovery

        return SkillDiscovery.analyze_command(goal)
    except Exception:
        return None


def classify(goal: str) -> str:
    """Returns ``evolution`` | ``single_tool`` | ``dag`` | ``unknown`` for a goal."""
    goal = (goal or "").strip()
    if not goal:
        return "unknown"
    if _evolution_request(goal):
        return "evolution"
    try:
        plan = create_plan(goal)
    except Exception:
        return "unknown"
    steps = plan.get("steps") or []
    if not steps:
        return "unknown"
    if len(steps) == 1 and steps[0].get("tool"):
        return "single_tool"
    return "dag"


class RouterResult(dict):
    """Envelope returned by :func:`route` (dict-compatible for easy JSON use)."""

    @property
    def route(self) -> str:
        return str(self.get("route") or "")

    @property
    def output(self) -> str:
        return str(self.get("output") or "")

    @property
    def success(self) -> bool:
        return bool(self.get("success"))


def run_plan(
    plan: Dict[str, Any],
    speak: Optional[Callable] = None,
    player: Any = None,
) -> RouterResult:
    """Executes an already-built plan step by step through the executor's dispatcher."""
    from agent.executor import _call_tool

    steps = plan.get("steps") or []
    results: List[Dict[str, Any]] = []
    success = True

    for step in steps:
        tool = step.get("tool")
        if not tool:
            results.append({"step": step.get("step"), "tool": None, "error": "Step has no tool."})
            success = False
            continue
        parameters = {key: value for key, value in step.items() if key not in ("step", "tool", "description")}
        try:
            output = _call_tool(str(tool), parameters, speak, player)
            results.append({"step": step.get("step"), "tool": tool, "output": str(output)[:4000]})
        except Exception as exc:
            success = False
            results.append({"step": step.get("step"), "tool": tool, "error": f"{type(exc).__name__}: {exc}"})

    return RouterResult(
        {
            "success": success,
            "route": "plan",
            "steps": len(steps),
            "results": results,
            "output": _summarise(results),
        }
    )


def _summarise(results: List[Dict[str, Any]]) -> str:
    lines = []
    for item in results:
        if item.get("error"):
            lines.append(f"Step {item.get('step')} ({item.get('tool')}) failed: {item['error']}")
        else:
            lines.append(str(item.get("output") or "").strip())
    return "\n".join(line for line in lines if line)


def route(
    goal: str,
    speak: Optional[Callable] = None,
    cancel_flag: Any = None,
    player: Any = None,
) -> RouterResult:
    """Classifies ``goal`` and dispatches it to the cheapest correct engine."""
    goal = (goal or "").strip()
    if not goal:
        return RouterResult({"success": False, "route": "unknown", "output": "No goal provided.", "goal": goal})

    decision = classify(goal)

    if decision == "evolution":
        try:
            from core.skill_discovery import SkillDiscovery

            forge = _evolution_request(goal) or {}
            result = SkillDiscovery.execute_forge(goal, forge.get("name"))
            message = str(result.get("message") or result.get("error") or "Skill evolution finished.")
            return RouterResult(
                {
                    "success": bool(result.get("success")),
                    "route": "evolution",
                    "goal": goal,
                    "output": message,
                    "skill": result.get("name", ""),
                    "detail": result,
                }
            )
        except Exception as exc:
            return RouterResult(
                {
                    "success": False,
                    "route": "evolution",
                    "goal": goal,
                    "output": f"Evolution route failed: {type(exc).__name__}: {exc}",
                }
            )

    if decision == "single_tool":
        plan = create_plan(goal)
        return run_plan(plan, speak=speak, player=player)

    if decision == "dag":
        try:
            from agent.executor import AgentExecutor

            output = AgentExecutor().execute(goal, speak=speak, cancel_flag=cancel_flag, player=player)
            return RouterResult(
                {"success": True, "route": "dag", "goal": goal, "output": str(output)}
            )
        except Exception as exc:
            return RouterResult(
                {
                    "success": False,
                    "route": "dag",
                    "goal": goal,
                    "output": f"DAG route failed: {type(exc).__name__}: {exc}",
                }
            )

    return RouterResult(
        {
            "success": False,
            "route": "unknown",
            "goal": goal,
            "output": "No plan could be constructed for this goal.",
        }
    )


def main() -> int:
    """CLI: ``python -m core.router "<goal>"`` prints the chosen route as JSON."""
    import sys

    goal = " ".join(sys.argv[1:]).strip()
    if not goal:
        print("usage: python -m core.router \"<goal>\"")
        return 2
    decision = classify(goal)
    print(json.dumps({"goal": goal, "route": decision}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
