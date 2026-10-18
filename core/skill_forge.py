"""
The Skill Forge: Autonomous Capability Synthesis Engine
Part of Project Ultron for Sudarshana AI.

Transforms natural language goals into fully architected, tested,
and hot-pluggable Python skills for Sudarshana AI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.user_paths import get_user_data_dir
from core.skill_crucible import SkillCrucible
from core.dynamic_registry import DynamicToolRegistry

logger = logging.getLogger("SkillForge")

CONFIG_DIR = get_user_data_dir() / "config"
API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"


def _get_gemini_api_key() -> str:
    """Retrieves the Gemini API key from api_keys.json or environment variables."""
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("gemini_api_key", "").strip()
                if key:
                    return key
        except Exception:
            pass
    return (os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")).strip()


class SkillForge:
    """Autonomous synthesizer of new Sudarshana AI skills."""

    @classmethod
    def forge_skill(
        cls,
        goal: str,
        skill_name: Optional[str] = None,
        context_hints: str = "",
        max_repair_attempts: int = 4,
    ) -> Dict[str, Any]:
        """
        Synthesizes a brand new skill from natural language, verifies it in the
        Crucible sandbox, auto-resolves pip packages, and hot-registers it.

        Hardened: every failure is journaled by ForgeMemory, recurring failure
        patterns are converted into lessons and injected back into the synthesizer
        and repair prompts, and the repair loop is given the full error history so
        it adapts instead of repeating the same broken approach.
        """
        logger.info(f"[Forge] Initiating skill synthesis for goal: '{goal}'")

        # Normalize skill name if provided
        name_hint = re.sub(r"[^a-zA-Z0-9_]", "_", (skill_name or "").lower()).strip("_")

        # Inject hard-won lessons + this goal's prior failure history (learning loop)
        try:
            from core import forge_memory as ForgeMemory  # type: ignore
        except Exception:
            ForgeMemory = None
        memory_blocks = []
        if ForgeMemory is not None:
            try:
                lessons = ForgeMemory.lessons_for(goal, limit=6)
                if lessons:
                    memory_blocks.append(lessons)
                prior = ForgeMemory.failure_digest(goal, limit=4)
                if prior:
                    memory_blocks.append(prior)
            except Exception as exc:
                logger.warning(f"[Forge] lesson injection failed: {exc}")

        effective_hints = "\n\n".join([b for b in [context_hints.strip(), *memory_blocks] if b]).strip()

        def _fail(stage: str, message: str, attempts: int, code: str = "", telemetry: Any = None) -> Dict[str, Any]:
            if ForgeMemory is not None:
                try:
                    ForgeMemory.record_failure(
                        goal=goal, stage=stage, error=message, attempts=attempts,
                        skill_name=skill_name or "", code=code, telemetry=telemetry,
                    )
                except Exception as exc:
                    logger.warning(f"[Forge] failure journal write failed: {exc}")
            return {"success": False, "stage": stage, "message": message, "attempts": attempts}

        # 1. Synthesize initial specification (with adaptive retries on transient errors)
        synthesis = cls._call_llm_synthesizer(goal, name_hint, effective_hints, retries=2)
        if not synthesis.get("success"):
            return _fail("synthesis", f"Skill synthesis generation failed: {synthesis.get('error')}", 1)

        manifest = synthesis["manifest"]
        code = synthesis["code"]
        test_cases = synthesis.get("test_cases", [{"input": {}}])
        actual_name = manifest.get("name", name_hint or "custom_skill")
        error_history: list[str] = []

        # 2. Iterative Verification & Self-Repair Loop
        total_passes = max_repair_attempts + 1
        for attempt in range(total_passes):
            logger.info(f"[Forge] Crucible verification attempt {attempt + 1}/{total_passes} for '{actual_name}'")

            # Stage A: AST Validation
            ast_ok, ast_err = SkillCrucible.validate_ast(code)
            if not ast_ok:
                error_history.append(f"[AST] {ast_err}")
                if attempt < max_repair_attempts:
                    logger.warning(f"[Forge] AST check failed ({ast_err}). Requesting repair from LLM...")
                    repair = cls._repair_code(code, ast_err, goal, history=error_history)
                    if repair.get("success"):
                        code = repair["code"]
                        continue
                return _fail("ast", f"Crucible AST rejected skill: {ast_err}", attempt + 1, code=code)

            # Stage B: Dependency Auto-Resolver — now repairable instead of fatal
            deps = SkillCrucible.extract_dependencies(code)
            deps_ok, deps_msg = SkillCrucible.resolve_dependencies(deps)
            if not deps_ok:
                err = f"Dependency resolution failed: {deps_msg}"
                error_history.append(f"[DEPS] {err}")
                if attempt < max_repair_attempts:
                    logger.warning(f"[Forge] {err}. Asking the LLM to remove/replace those imports...")
                    repair = cls._repair_code(
                        code,
                        err + " Replace the missing/uninstallable imports with standard-library or already installed alternatives.",
                        goal,
                        history=error_history,
                    )
                    if repair.get("success"):
                        code = repair["code"]
                        continue
                return _fail("dependencies", err, attempt + 1, code=code)

            # Stage C: Sandboxed Execution Tests
            test_ok, test_msg, test_telemetry = SkillCrucible.run_sandbox_test(code, test_cases)
            if not test_ok:
                error_history.append(f"[SANDBOX] {test_msg}")
                if attempt < max_repair_attempts:
                    logger.warning(f"[Forge] Sandbox tests failed ({test_msg}). Requesting repair from LLM...")
                    repair = cls._repair_code(code, test_msg, goal, history=error_history)
                    if repair.get("success"):
                        code = repair["code"]
                        continue
                return _fail(
                    "sandbox",
                    f"Crucible Sandbox tests failed: {test_msg}",
                    attempt + 1,
                    code=code,
                    telemetry=test_telemetry,
                )

            # All stages passed!
            break

        # 3. Commit as a Native Codebase Feature in features/ (Autonomous Self-Evolution)
        features_dir = DynamicToolRegistry.get_skills_directory()
        features_dir.mkdir(parents=True, exist_ok=True)

        # Prepare triggers & aliases
        triggers = list(manifest.get("triggers", []))
        if goal and goal.strip() not in triggers:
            triggers.append(goal.strip())

        clean_goal = re.sub(
            r"^(?:please\s+|can\s+you\s+|use\s+(?:the\s+)?(?:skill|feature)\s+to\s+|run\s+(?:the\s+)?(?:skill|feature)\s+to\s+|test\s+(?:the\s+)?(?:skill|feature)\s+to\s+)",
            "",
            goal.lower().strip()
        )
        if clean_goal and clean_goal not in triggers:
            triggers.append(clean_goal)

        name_words_trigger = actual_name.replace("_", " ")
        if name_words_trigger not in triggers:
            triggers.append(name_words_trigger)

        aliases = list(manifest.get("aliases", []))
        clean_alias = actual_name.replace("_", "")
        if clean_alias not in aliases:
            aliases.append(clean_alias)

        manifest["name"] = actual_name
        manifest["triggers"] = list(dict.fromkeys(triggers))
        manifest["aliases"] = list(dict.fromkeys(aliases))
        manifest["created_at"] = time.time()
        manifest["version"] = "1.0.0"
        manifest["author"] = "Project Ultron Autonomous Self-Evolution Engine"
        manifest["active"] = True

        # Build clean native feature code with embedded FEATURE_METADATA
        feature_code = code
        if "FEATURE_METADATA" not in feature_code:
            meta_str = repr(manifest)
            header = (
                f'"""\n'
                f'Feature: {actual_name}\n'
                f'Description: {manifest.get("description", "")}\n'
                f'Autonomous Evolutionary Capability synthesized by Sudarshana AI.\n'
                f'"""\n\n'
                f'FEATURE_METADATA = {meta_str}\n\n'
            )
            feature_code = header + feature_code

        # Primary native module: features/{actual_name}.py
        feature_py_file = features_dir / f"{actual_name}.py"
        try:
            with open(feature_py_file, "w", encoding="utf-8") as f:
                f.write(feature_code)

            # Update features/__init__.py for self-evolving codebase integration
            init_file = features_dir / "__init__.py"
            try:
                init_content = init_file.read_text(encoding="utf-8") if init_file.exists() else ""
                import_stmt = f"from . import {actual_name}\n"
                if import_stmt not in init_content:
                    with open(init_file, "a", encoding="utf-8") as f_init:
                        f_init.write(import_stmt)
            except Exception as e_init:
                logger.warning(f"[Forge] Could not update features/__init__.py: {e_init}")

            # Also maintain feature package directory for telemetry and test cases
            target_dir = features_dir / actual_name
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4)
            with open(target_dir / "skill.py", "w", encoding="utf-8") as f:
                f.write(feature_code)
            with open(target_dir / "test_cases.json", "w", encoding="utf-8") as f:
                json.dump(test_cases, f, indent=4)

            # 4. Hot-Load into Dynamic Registry
            DynamicToolRegistry.initialize()
            if not DynamicToolRegistry.has_tool(actual_name):
                raise RuntimeError(f"Generated feature '{actual_name}' was not registered.")

            if ForgeMemory is not None:
                try:
                    ForgeMemory.record_success(goal=goal, skill_name=actual_name, attempts=attempt + 1)
                except Exception as exc:
                    logger.warning(f"[Forge] success journal write failed: {exc}")

            return {
                "success": True,
                "name": actual_name,
                "description": manifest.get("description", ""),
                "skill_path": str(feature_py_file),
                "message": f"Successfully forged and activated native feature '{actual_name}'! Verified via Crucible sandbox.",
                "manifest": manifest,
            }
        except Exception as e:
            return _fail("commit", f"Failed saving synthesized feature: {e}", total_passes, code=code)

    @classmethod
    def _parse_json_response(cls, text: str) -> Dict[str, Any]:
        """Robustly extracts and parses a JSON object from model output, ignoring any extra trailing text."""
        clean = (text or "").strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*\n?", "", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\n?```\s*$", "", clean).strip()

        # 1. Try direct json.loads
        try:
            data = json.loads(clean)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # 2. Use JSONDecoder.raw_decode starting from first '{' (skips trailing notes/extra data)
        start_idx = clean.find("{")
        if start_idx != -1:
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(clean[start_idx:])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        # 3. Match outermost balanced { and }
        if start_idx != -1:
            for end_idx in range(len(clean) - 1, start_idx, -1):
                if clean[end_idx] == "}":
                    candidate = clean[start_idx:end_idx + 1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        continue

        raise ValueError("Could not extract a valid JSON object from LLM output.")

    @classmethod
    def _call_llm_synthesizer(cls, goal: str, name_hint: str, context_hints: str, retries: int = 0) -> Dict[str, Any]:
        """Synthesizes with adaptive retries so transient rate-limits never kill the forge."""
        attempt = 0
        delay = 1.5
        last: Dict[str, Any] = {"success": False, "error": "synthesis not attempted"}
        while attempt <= max(0, retries):
            last = cls._synthesize_once(goal, name_hint, context_hints)
            if last.get("success"):
                return last
            attempt += 1
            if attempt <= retries:
                logger.warning(f"[Forge] Synthesis attempt {attempt} failed ({last.get('error')}); retrying in {delay:.1f}s")
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        return last

    @classmethod
    def _synthesize_once(cls, goal: str, name_hint: str, context_hints: str) -> Dict[str, Any]:
        """Prompts Gemini to generate the complete skill package JSON."""
        system_instructions = """You are the Sudarshana AI Autonomous Skill Architect ("Project Ultron").
Your mission is to invent, architect, and write a complete, standalone, production-ready Python skill plugin.

Skill Architecture Guidelines:
1. Entry point MUST be `def execute(**kwargs)` or `async def execute(**kwargs)`.
2. Must be clean, robust Python with error handling (try/except) and type annotations.
3. Default Parameter Handling:
   - In `execute(**kwargs)`, ALWAYS assign safe fallback defaults to all expected parameters (e.g. `query = kwargs.get('query') or kwargs.get('search') or 'headphones'`).
   - If called with empty kwargs `{}` (such as during sandbox verification), the skill MUST execute cleanly without throwing KeyError or TypeError.
4. Resilient Network & Safe SSL Handling:
   - When external live data or web downloads are needed, prefer `requests` with `timeout=8, verify=False`, OR if using `urllib`, ALWAYS bypass Windows SSL verification via `import ssl; ctx = ssl._create_unverified_context()` because Python on Windows frequently throws `[SSL: CERTIFICATE_VERIFY_FAILED]`.
   - NEVER require or assume environment API keys (e.g. `GIPHY_API_KEY`, `OPENAI_API_KEY`). Skills must be 100% self-contained and run out of the box using public open APIs (such as Tenor public key `LIVDSRZULELA` or open REST) or local Python logic.
   - If any network call fails or times out, ALWAYS catch generic `Exception` and supply a working fallback so `execute()` NEVER returns an `{'error': ...}` dictionary.
   - Do NOT use heavy scrapers (avoid selenium/playwright).
5. Visual Deliverables, Images, GIFs, & UI Cards:
   - If the user asks for images, drawings, graphics, headphones, cars, animals, cartoons, plots, scorecards, charts, or GIFs:
     a) ALWAYS produce an actual deliverable image file (.png or .gif) saved to:
        `output_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'SudarshanaAI', 'deliverables')`
        `os.makedirs(output_dir, exist_ok=True)`
        `image_path = os.path.join(output_dir, f'{actual_name}_output.png')`
     b) For diagrams, illustrations, charts, or tech visuals: Generate the visual NATIVELY using `PIL` (`from PIL import Image, ImageDraw, ImageFont`) or `matplotlib` (`import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt`).
        Style it with a sleek cyberpunk dark theme: dark slate background `#0B0F19` or `#030712`, glowing cyan `#00F0FF`, ice cyan `#38BDF8`, emerald `#10B981`, and white `#FFFFFF`.
     c) For web images/GIFs: Attempt downloading using safe SSL context or requests, but if download fails or if network is unavailable, IMMEDIATELY fall back to drawing a crisp high-tech visual deliverable using PIL/matplotlib so execution always succeeds and displays on screen.
     d) Return format for visuals:
        `return {'image_path': image_path, 'title': '...', 'summary': '...'}`
        This triggers Sudarshana Chakra's HUD Result Wing to immediately display the card!
6. Output Format:
   Output MUST be clean JSON with exact structure:
{
    "manifest": {
        "name": "snake_case_feature_name",
        "aliases": ["alias_1", "alias_2"],
        "description": "Concise, actionable description of when and how Gemini Live should call this feature",
        "triggers": [
            "direct trigger phrase 1",
            "natural variation 2",
            "query command 3"
        ],
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "param_name": {
                    "type": "STRING|INTEGER|NUMBER|BOOLEAN",
                    "description": "What this parameter is"
                }
            },
            "required": []
        }
    },
    "code": "Full python source code including imports and def execute(**kwargs)",
    "test_cases": [
        {
            "input": {}
        }
    ]
}
Return ONLY this JSON object with no markdown fences around it.
"""

        prompt = f"""Synthesize a new skill for the following user request:
Goal: {goal}
Preferred Name: {name_hint or 'auto_generate'}
Additional Context: {context_hints}
"""

        gemini_key = _get_gemini_api_key()
        if gemini_key:
            try:
                from google import genai
                g_client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
                for model_name in ("gemini-3.8-flash", "gemini-flash-latest"):
                    try:
                        resp = g_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={
                                "temperature": 0.2,
                                "system_instruction": system_instructions,
                                "response_mime_type": "application/json"
                            }
                        )
                        raw = getattr(resp, "text", "") or ""
                        data = cls._parse_json_response(raw)
                        if "manifest" in data and "code" in data:
                            data["success"] = True
                            return data
                    except Exception as e:
                        logger.warning(f"[Forge] Model {model_name} failed: {e}")
                        continue
            except Exception as exc:
                logger.error(f"[Forge] Gemini client error: {exc}")

        # Fallback to Unified llm_client if available
        try:
            from llm_client import client as unified_client
            resp = unified_client.chat(
                prompt=prompt,
                system=system_instructions,
                max_tokens=8192,
                temperature=0.2,
            )
            data = cls._parse_json_response(resp)
            if not isinstance(data.get("manifest"), dict) or not isinstance(data.get("code"), str):
                raise ValueError("Unified LLM response must contain a manifest object and code string.")
            data["success"] = True
            return data
        except Exception as fallback_exc:
            return {"success": False, "error": f"LLM synthesis failed: {fallback_exc}"}

    @classmethod
    def _repair_code(
        cls,
        broken_code: str,
        error_msg: str,
        goal: str,
        history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Asks LLM to fix syntax or sandbox runtime errors.

        `history` carries every error seen so far on this goal so the repair is
        cumulative instead of forgetting what already failed.
        """
        history_block = ""
        prior = [str(h) for h in (history or []) if str(h).strip()]
        if prior:
            history_block = "\nERROR HISTORY ON THIS SKILL (all previous attempts failed — change strategy, do not repeat these):\n"
            history_block += "\n".join(f"{i}. {h[:400]}" for i, h in enumerate(prior[-6:], 1))
            history_block += "\n"

        prompt = f"""You are repairing a Python skill generated for Sudarshana AI ("Project Ultron").
The skill failed verification in the Crucible sandbox.
User Goal: {goal}
Verification Error: {error_msg}
{history_block}
Broken Code:
```python
{broken_code}
```

Critical Repair Instructions:
1. Ensure `def execute(**kwargs)` handles empty or missing kwargs with safe defaults.
2. If using `matplotlib`, ensure `import matplotlib; matplotlib.use('Agg')` is placed before `pyplot`.
3. If making HTTP requests, use `requests` with `timeout=8, verify=False` or `urllib` with `ssl._create_unverified_context()`. NEVER assume custom library exceptions or unset API keys (like GIPHY_API_KEY).
4. If downloading an image or media fails or has SSL errors, NEVER just return an error dictionary. Generate the image natively using PIL (Pillow) or matplotlib and save to `SudarshanaAI/deliverables/<name>.png`.
5. Return a clean deliverable dictionary with `'image_path'`, `'title'`, `'summary'` if visual, or clean structured output.
6. The test runner checks that the returned value does NOT contain an `'error'` key. Do not return `{{'error': '...'}}`. If an error occurs, provide a graceful fallback result.
7. Use ONLY the Python standard library plus packages that are already installed (requests, pillow, numpy, matplotlib, bs4, lxml, psutil). Do not import exotic third-party packages.
8. Return ONLY a JSON object:
{{
    "code": "Fully corrected, runnable Python code"
}}
"""
        gemini_key = _get_gemini_api_key()
        if gemini_key:
            try:
                from google import genai
                g_client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
                for model_name in ("gemini-3.8-flash", "gemini-flash-latest"):
                    try:
                        resp = g_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={"temperature": 0.1, "response_mime_type": "application/json"}
                        )
                        raw = getattr(resp, "text", "") or ""
                        data = cls._parse_json_response(raw)
                        if "code" in data:
                            data["success"] = True
                            return data
                    except Exception as e:
                        logger.warning(f"[Forge] Repair model {model_name} failed: {e}")
                        continue
            except Exception as exc:
                logger.error(f"[Forge] Repair Gemini error: {exc}")

        return {"success": False, "error": "Repair attempt failed."}
