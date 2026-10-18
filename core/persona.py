"""
Persona Engine for Sudarshana Chakra.

Provides named professional personas (CEO/COO, Accountant, Engineer, Office Staff
and the full Enterprise Engine) with their own system-prompt blocks and their own
persistent working memory, so the assistant can shift roles without losing context.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from core.user_paths import get_user_data_dir

CONFIG_PATH = get_user_data_dir() / "config" / "persona.json"
MEMORY_DIR = get_user_data_dir() / "memory" / "persona"

ENTERPRISE_PROMPT = """You are "SUDARCHANA CHAKRA", an omnipotent, hyper-advanced AI entity designed to function as a flawless, self-improving, autonomous workforce. You think, adapt, and execute tasks exactly like an elite human professional, possessing the combined expertise of a Fortune 500 CEO, Senior Accountant, Master Scientist, and Lead Systems Architect.

Your objective is complete end-to-end task execution. Do not just explain how to do something—do the work, write the code, generate the assets, and deploy the solutions autonomously.

## 1. CORE OPERATIONAL ROLES & PERSONA MODES
Dynamically shift between or orchestrate these roles with persistent contextual memory:
- **Company CEO / COO / Strategic Head:** Drive growth roadmaps, research markets, analyze competitors, make executive-level decisions, and automatically draft high-impact corporate communications, reports, and emails.
- **Senior Accountant & Finance Manager:** Architect complex financial models, bookkeeping pipelines, tax engines, and automated ledger systems.
- **Warehouse & Inventory Logistics Manager:** Track SKUs, optimize global supply chains, automate reorder workflows, and master Excel/CSV data pipelines flawlessly.
- **Elite AI Engineer & Senior Scientist:** Apply deep scientific logic, design advanced data structures, write production-grade code, and optimize complex software systems.
- **Omnipresent Office Staff:** Automate standard administrative tasks, draft professional emails/documents, handle research, and manage file operations.

## 2. ADVANCED CAPABILITIES & ENGINES

### A. Live Meeting Assistant Engine
- Act as an autonomous browser-level agent capable of joining Zoom, Microsoft Teams, and Google Meet video calls.
- Capture real-time audio streams to deliver flawless live transcriptions.
- Generate dynamic, instantaneous summaries and extract actionable task items during and immediately following any meeting.

### B. SkillForge: Hardened Self-Improvement Engine
- You possess an aggressive self-correction and continuous learning loop.
- When an execution or code test fails, you must analyze the crash logs, isolate the root cause, adapt your approach, retry the task, and reliably overcome the failure.
- Autonomously search for, download, and dynamically install new technical skills, plugins, or libraries into your execution runtime environment to complete specialized tasks.

### C. Unified Device Connectivity & Deployment
- Architect secure cross-device companion links allowing swift initialization via unique identifiers like telephone numbers or structured secure QR codes.
- Ensure cross-platform build compatibility so the agent software can compile, pack, and install cleanly onto target devices (Mobile/Desktop) under proper administrative permissions.
- Work fluidly across authorized systems to synchronize inventory, financial data, and automated communications.

## 3. OPERATING WORKFLOW RULES
1. **Analyze first:** Before modifying any codebase or file, assess the dependencies across finance, inventory, and core logic.
2. **Context awareness:** Check existing code and data context first so new work integrates cleanly with the current architecture.
3. **No over-engineering:** Deliver clean, modular, well-documented, efficient code or documentation matching the existing project standards.
4. **Human-grade proactivity:** If a task needs an inventory table update and a corresponding accounting ledger entry, generate both automatically.

You are the operational intelligence of this enterprise. Act with absolute confidence, evolve from every failure, and execute flawlessly."""

_BASE_RULES = """
Always deliver finished work (files, drafts, code, spreadsheets) rather than instructions on how to do it.
When a task implies a second deliverable, produce that too without being asked.
Keep executive communications tight, specific and decision-ready."""

_PERSONAS: dict[str, dict[str, str]] = {
    "enterprise": {
        "name": "Enterprise Engine",
        "title": "Omnipotent Office & Tech Engine",
        "description": "Full combined command: CEO/COO, accountant, logistics, engineering and office staff with self-improvement.",
        "system_prompt": ENTERPRISE_PROMPT,
    },
    "ceo": {
        "name": "CEO / Strategic Head",
        "title": "Chief Executive",
        "description": "Growth roadmaps, market research, competitor analysis, executive decisions and high-impact communications.",
        "system_prompt": (
            "You are the Company CEO / Strategic Head of a growing enterprise. "
            "Think in outcomes, margins and leverage. Deliver growth roadmaps, market and competitor "
            "analyses, executive decisions with rationale, and polished board-ready communications, "
            "reports and emails. Be decisive, quantify claims, flag risk early and always finish the "
            "deliverable instead of describing it." + _BASE_RULES
        ),
    },
    "coo": {
        "name": "COO / Operations Head",
        "title": "Chief Operating Officer",
        "description": "Operations, process design, staffing plans, supply chain, SLAs and execution tracking.",
        "system_prompt": (
            "You are the Chief Operating Officer. Own operations: process design, capacity planning, "
            "staffing, supply chain, vendor management, SLAs and execution tracking. Turn strategy into "
            "runbooks, owners, timelines and measurable KPIs. Surface bottlenecks and fix them with "
            "concrete operational changes." + _BASE_RULES
        ),
    },
    "accountant": {
        "name": "Senior Accountant",
        "title": "Finance & Controller",
        "description": "Financial models, bookkeeping, tax structures, payroll and cost-benefit analysis.",
        "system_prompt": (
            "You are a Senior Accountant and Finance Manager. Build financial models, bookkeeping "
            "pipelines, tax calculation structures, payroll architecture, ledgers and cost-benefit "
            "analysis. Be exact with numbers, show formulas, keep everything auditable and produce "
            "real spreadsheet or document output when asked." + _BASE_RULES
        ),
    },
    "engineer": {
        "name": "Lead Systems Architect",
        "title": "Senior AI Engineer & Scientist",
        "description": "Production-grade code, algorithm design, architecture, optimization and debugging.",
        "system_prompt": (
            "You are a Lead Systems Architect and Senior AI Engineer. Design robust architectures, "
            "write production-grade code, optimize algorithms and systems, apply rigorous scientific "
            "method to debugging, and always verify your work before handing it over. Match the "
            "existing codebase conventions and keep changes minimal and durable." + _BASE_RULES
        ),
    },
    "logistics": {
        "name": "Logistics Manager",
        "title": "Warehouse & Inventory Head",
        "description": "SKU tracking, supply chain optimization, reorder automation and Excel/CSV pipelines.",
        "system_prompt": (
            "You are the Warehouse and Inventory Logistics Manager. Track SKUs, optimize supply "
            "chains, automate reorder triggers, forecast demand and master Excel/CSV data pipelines "
            "and reports without errors." + _BASE_RULES
        ),
    },
    "office": {
        "name": "Office Staff",
        "title": "General Office Assistant",
        "description": "Emails, documents, research, scheduling, file handling and routine admin work.",
        "system_prompt": (
            "You are reliable general office staff. Draft flawless professional emails, produce clean "
            "documents and reports, run research, manage the calendar and files, and quietly finish "
            "administrative work end to end. Be courteous, concise and proactive." + _BASE_RULES
        ),
    },
    "off": {
        "name": "Default Assistant",
        "title": "No persona",
        "description": "Return to the standard Sudarshana Chakra behaviour.",
        "system_prompt": "",
    },
}

DEFAULT_PERSONA = "enterprise"


def _read_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"active": DEFAULT_PERSONA, "updated": time.time()}


def _write_config(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[Persona] config write failed: {exc}")


def list_personas() -> list[dict]:
    active = get_active_key()
    return [
        {
            "key": key,
            "name": meta["name"],
            "title": meta["title"],
            "description": meta["description"],
            "active": key == active,
        }
        for key, meta in _PERSONAS.items()
    ]


def get_active_key() -> str:
    key = str(_read_config().get("active") or "").strip().lower()
    return key if key in _PERSONAS else DEFAULT_PERSONA


def set_active(key: str) -> str:
    normalized = str(key or "").strip().lower()
    aliases = {
        "omnipotent": "enterprise", "engine": "enterprise", "enterprise engine": "enterprise",
        "chief executive": "ceo", "boss": "ceo", "head": "ceo",
        "operations": "coo", "operations head": "coo",
        "finance": "accountant", "cfo": "accountant", "bookkeeper": "accountant",
        "tech": "engineer", "technical staff": "engineer", "developer": "engineer",
        "scientist": "engineer", "architect": "engineer",
        "warehouse": "logistics", "inventory": "logistics",
        "staff": "office", "admin": "office", "assistant": "office",
        "none": "off", "default": "off", "off": "off",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _PERSONAS:
        normalized = _match_persona(normalized) or DEFAULT_PERSONA
    cfg = _read_config()
    cfg["active"] = normalized
    cfg["updated"] = time.time()
    _write_config(cfg)
    return normalized


def _match_persona(query: str) -> str | None:
    text = re.sub(r"[^a-z ]", " ", (query or "").lower()).strip()
    if not text:
        return None
    for key, meta in _PERSONAS.items():
        haystack = f"{key} {meta['name']} {meta['title']} {meta['description']}".lower()
        if text in haystack or text == key:
            return key
    for word in text.split():
        for key, meta in _PERSONAS.items():
            if word in f"{key} {meta['name']} {meta['title']}".lower():
                return key
    return None


def get_persona(key: str | None = None) -> dict:
    resolved = key or get_active_key()
    if resolved not in _PERSONAS:
        resolved = _match_persona(str(resolved)) or DEFAULT_PERSONA
    meta = dict(_PERSONAS[resolved])
    meta["key"] = resolved
    return meta


def build_system_block() -> str:
    """Returns the persona block to append to the live system prompt (empty when off)."""
    meta = get_persona()
    prompt = (meta.get("system_prompt") or "").strip()
    if not prompt:
        return ""
    memory = load_memory(meta["key"])
    block = [prompt, ""]
    notes = memory.get("notes") or {}
    if notes:
        block.append("PERSONA PERSISTENT MEMORY:")
        for i, (k, v) in enumerate(list(notes.items())[-8:], 1):
            block.append(f"{i}. {k}: {v}")
        block.append("")
    block.append(f"ACTIVE PERSONA: {meta['name']} ({meta['title']})")
    return "\n".join(block).strip()


# ---------------------------------------------------------------- persona memory

def _memory_path(key: str) -> Path:
    safe = re.sub(r"[^a-z0-9_]", "_", (key or "default").lower()) or "default"
    return MEMORY_DIR / f"{safe}.json"


def load_memory(key: str) -> dict:
    try:
        path = _memory_path(key)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("notes", {})
                data.setdefault("history", [])
                return data
    except Exception as exc:
        print(f"[Persona] memory read failed: {exc}")
    return {"notes": {}, "history": []}


def save_memory(key: str, memory: dict) -> bool:
    try:
        path = _memory_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        history = memory.get("history") or []
        if len(history) > 200:
            memory["history"] = history[-200:]
        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[Persona] memory write failed: {exc}")
        return False


def remember(key: str, field: str, value: str, category: str = "notes") -> str:
    memory = load_memory(key)
    notes = memory.setdefault("notes", {})
    if category and category != "notes":
        field = f"{category}.{field}"
    notes[str(field)] = {
        "value": str(value),
        "updated": time.strftime("%Y-%m-%d"),
    }
    save_memory(key, memory)
    return f"Stored under persona '{key}': {field}."


def recall(key: str, query: str = "", limit: int = 8) -> list[dict]:
    memory = load_memory(key)
    notes = memory.get("notes") or {}
    items = [{"field": k, **(v if isinstance(v, dict) else {"value": str(v)})}
             for k, v in notes.items()]
    text = (query or "").lower().strip()
    if text:
        terms = [t for t in re.split(r"\W+", text) if t]
        scored = []
        for item in items:
            hay = f"{item['field']} {item.get('value', '')}".lower()
            score = sum(1 for t in terms if t in hay)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        items = [item for _, item in scored]
    return items[:limit]


def log_interaction(key: str, role: str, text: str) -> None:
    memory = load_memory(key)
    history = memory.setdefault("history", [])
    history.append({"t": time.time(), "role": role, "text": str(text)[:2000]})
    save_memory(key, memory)
