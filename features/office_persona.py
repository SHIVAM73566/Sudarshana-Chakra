"""
Feature: office_persona
Description: Switches between professional personas (CEO/COO, Accountant, Engineer, Logistics,
Office Staff, Enterprise Engine), remembers and recalls working memory, and drafts finished
professional communications and documents in the active persona's voice.
"""

FEATURE_METADATA = {
    "name": "office_persona",
    "aliases": [
        "persona mode", "office staff mode", "ceo mode", "accountant mode", "engineer mode",
        "switch persona", "set persona", "persona memory", "draft email", "draft document",
    ],
    "description": (
        "Professional persona engine. Switches the assistant between CEO/COO, COO Operations, "
        "Senior Accountant, Lead Systems Architect, Logistics Manager, Office Staff and the full "
        "Enterprise Engine; stores and recalls persistent persona memory; and drafts finished "
        "professional emails, documents, reports and messages written in the active persona's voice."
    ),
    "triggers": [
        "switch to accountant mode",
        "act as the ceo",
        "use office staff mode",
        "remember that this client prefers invoices",
        "what do you remember about the vendor",
        "draft an email to the supplier",
        "write a professional document",
        "which persona are you in",
        "list personas",
        "set persona to engineer",
    ],
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "set | get | list | remember | recall | draft | status. Defaults to draft when 'brief' is given, otherwise status.",
            },
            "persona": {"type": "STRING", "description": "Persona key to activate: enterprise, ceo, coo, accountant, engineer, logistics, office or off."},
            "field": {"type": "STRING", "description": "For remember: the field name to store (e.g. 'client', 'invoice_format')."},
            "value": {"type": "STRING", "description": "For remember: the value to store under 'field'."},
            "query": {"type": "STRING", "description": "For recall: what to search the persona memory for."},
            "kind": {"type": "STRING", "description": "For draft: email | message | document | report | note. Defaults to email."},
            "brief": {"type": "STRING", "description": "For draft: what the communication should say / cover."},
            "to": {"type": "STRING", "description": "For draft: recipient name or address."},
            "subject": {"type": "STRING", "description": "For draft: subject or title."},
            "tone": {"type": "STRING", "description": "For draft: formal | firm | friendly | apologetic | persuasive. Defaults to formal."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

import os
import re
import time
from pathlib import Path


def _persona():
    from core import persona
    return persona


def _deliverables_dir() -> Path:
    try:
        from core.user_paths import get_user_data_dir
        base = get_user_data_dir() / "deliverables" / "persona_docs"
    except Exception:
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "SudarshanaAI" / "deliverables" / "persona_docs"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base


def _api_key() -> str:
    try:
        from core.skill_forge import _get_gemini_api_key
        return _get_gemini_api_key()
    except Exception:
        return ""


def _notes_text(memory: dict) -> str:
    notes = (memory or {}).get("notes") or {}
    if not notes:
        return ""
    lines = []
    for k, v in list(notes.items())[-12:]:
        value = v.get("value") if isinstance(v, dict) else v
        lines.append(f"- {k}: {value}")
    return "\n".join(lines)


def _status_payload(persona, key=None):
    meta = persona.get_persona(key)
    mem = persona.load_memory(meta["key"])
    notes = mem.get("notes") or {}
    return {
        "active_persona": meta["key"],
        "name": meta["name"],
        "title": meta["title"],
        "description": meta["description"],
        "memory_fields": len(notes),
        "memory_preview": _notes_text(mem),
    }


def _draft_with_llm(persona, kind: str, brief: str, to: str, subject: str, tone: str):
    """Writes the finished deliverable in the active persona's voice."""
    meta = persona.get_persona()
    mem = persona.load_memory(meta["key"])
    key = _api_key()

    persona_block = (meta.get("system_prompt") or "").strip() or (
        "You are Sudarshana Chakra, a reliable professional assistant."
    )
    memory_block = _notes_text(mem)
    if memory_block:
        persona_block += "\n\nPERSISTENT WORKING MEMORY:\n" + memory_block

    tone = (tone or "formal").strip().lower()
    kind_norm = {
        "mail": "email", "msg": "message", "letter": "document",
        "memo": "document", "doc": "document", "summary": "report",
    }.get((kind or "email").strip().lower(), (kind or "email").strip().lower())
    if kind_norm not in ("email", "message", "document", "report", "note"):
        kind_norm = "email"

    labels = {
        "email": "professional email",
        "message": "short professional message",
        "document": "professional document",
        "report": "professional report",
        "note": "concise professional note",
    }

    user_prompt = f"""Write the finished {labels[kind_norm]} now. Do not describe how to write it — output the text itself.

Tone: {tone}
Recipient: {to or "not specified"}
Subject / title: {subject or "not specified"}
What it must cover: {brief}

Rules:
- Write in the voice and role of the active persona above.
- Use any matching facts from the working memory (client names, formats, preferences).
- If the brief lacks a required fact, write a sensible professional placeholder in [square brackets] instead of asking a question.
- Plain text only. No markdown fences, no preamble, no explanations."""

    if not key:
        return None, "No Gemini API key is configured (config/api_keys.json -> gemini_api_key)."

    try:
        from google import genai
        client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
        last_error = None
        for model_name in ("gemini-3.8-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config={
                        "system_instruction": persona_block,
                        "temperature": 0.5,
                    },
                )
                text = (getattr(resp, "text", "") or "").strip()
                if text:
                    return text, None
                last_error = f"{model_name} returned empty output"
            except Exception as exc:
                last_error = str(exc)
        return None, last_error or "all models failed"
    except Exception as exc:
        return None, str(exc)


def _fallback_draft(kind_norm: str, brief: str, to: str, subject: str) -> str:
    """Deterministic skeleton so the tool still produces a deliverable offline."""
    lines = []
    if kind_norm == "email":
        if to:
            lines.append(f"Dear {to},")
            lines.append("")
        lines.append(brief or "Please find below the requested information.")
        lines.append("")
        lines.append("Let me know if you need anything further.")
        lines.append("")
        lines.append("Regards,")
        lines.append("Sudarshana Chakra")
    elif kind_norm == "message":
        lines.append(brief or "Following up as discussed.")
    else:
        lines.append(subject or "Report")
        lines.append("=" * max(8, len(subject or "Report")))
        lines.append("")
        lines.append(brief or "")
        lines.append("")
        lines.append("Prepared by: Sudarshana Chakra")
    return "\n".join(lines)


def execute(**kwargs):
    """Persona engine: switch roles, remember/recall working memory, draft finished documents."""
    persona = _persona()
    action = str(kwargs.get("action") or "").strip().lower()
    p_persona = str(kwargs.get("persona") or kwargs.get("mode") or "").strip()
    field = str(kwargs.get("field") or kwargs.get("key") or "").strip()
    value = str(kwargs.get("value") or kwargs.get("content") or "").strip()
    query = str(kwargs.get("query") or kwargs.get("search") or "").strip()
    brief = str(kwargs.get("brief") or kwargs.get("text") or kwargs.get("topic") or "").strip()
    kind = str(kwargs.get("kind") or kwargs.get("type") or "email").strip()
    to = str(kwargs.get("to") or "").strip()
    subject = str(kwargs.get("subject") or kwargs.get("title") or "").strip()
    tone = str(kwargs.get("tone") or "formal").strip()

    if not action:
        if brief or subject:
            action = "draft"
        elif p_persona:
            action = "set"
        elif field and value:
            action = "remember"
        else:
            action = "status"

    # ------------------------------------------------------------------ list
    if action == "list":
        items = persona.list_personas()
        msg = "Available personas:\n" + "\n".join(
            f"- {i['key']}: {i['name']} — {i['description']}" + (" (ACTIVE)" if i["active"] else "")
            for i in items
        )
        return {"success": True, "summary": f"{len(items)} personas available.", "output": msg, "personas": items}

    # ------------------------------------------------------------------- set
    if action in ("set", "switch", "use", "activate"):
        if not p_persona:
            return {
                "success": False,
                "error": "No persona named. Use action='set' with persona= one of: "
                + ", ".join(p["key"] for p in persona.list_personas()),
            }
        resolved = persona.set_active(p_persona)
        meta = persona.get_persona()
        mem = persona.load_memory(resolved)
        msg = f"Persona switched to '{meta['name']}' ({meta['title']}). Memory fields: {len(mem.get('notes') or {})}."
        return {"success": True, "summary": msg, "output": msg, "status": _status_payload(persona)}

    # ------------------------------------------------------------------ get
    if action in ("get", "whoami", "which"):
        status = _status_payload(persona)
        msg = (
            f"Active persona: {status['name']} ({status['title']}).\n"
            f"{status['description']}\n"
            f"Stored memory fields: {status['memory_fields']}."
        )
        return {"success": True, "summary": msg, "output": msg, "status": status}

    # --------------------------------------------------------------- status
    if action == "status":
        status = _status_payload(persona)
        msg = (
            f"Persona: {status['name']} ({status['title']}). "
            f"Memory fields: {status['memory_fields']}."
        )
        if status["memory_preview"]:
            msg += "\nMemory:\n" + status["memory_preview"]
        return {"success": True, "summary": msg, "output": msg, "status": status}

    # ------------------------------------------------------------- remember
    if action in ("remember", "rememberthat", "store", "save"):
        if not field or not value:
            return {"success": False, "error": "remember needs both 'field' and 'value'."}
        active = persona.get_active_key()
        note = persona.remember(active, field, value)
        return {"success": True, "summary": note, "output": note, "persona": active}

    # --------------------------------------------------------------- recall
    if action in ("recall", "lookup", "search", "find"):
        active = persona.get_active_key()
        if not query:
            return {"success": False, "error": "recall needs a 'query'."}
        items = persona.recall(active, query)
        if not items:
            msg = f"Nothing stored yet for persona '{active}'." + (f" matching '{query}'." if query else ".")
            return {"success": True, "summary": msg, "output": msg, "items": []}
        msg = f"Persona '{active}' memory:\n" + "\n".join(
            f"- {i['field']}: {i.get('value', '')}" for i in items
        )
        return {"success": True, "summary": f"{len(items)} memory entries.", "output": msg, "items": items}

    # ---------------------------------------------------------------- draft
    if action in ("draft", "write", "compose", "email", "document", "report"):
        if not brief and not subject:
            return {"success": False, "error": "draft needs a 'brief' (what to write) or a 'subject'."}

        kind_norm = {
            "mail": "email", "msg": "message", "letter": "document", "memo": "document",
            "doc": "document", "summary": "report", "email": "email", "message": "message",
            "document": "document", "report": "report", "note": "note",
        }.get(kind.lower(), "email")

        text, err = _draft_with_llm(persona, kind_norm, brief, to, subject, tone)
        used_llm = bool(text)
        if not text:
            text = _fallback_draft(kind_norm, brief, to, subject)

        meta = persona.get_persona()
        safe_subject = re.sub(r"[^A-Za-z0-9 _-]", "", (subject or brief or kind_norm))[:60].strip().replace(" ", "_")
        if not safe_subject:
            safe_subject = kind_norm
        ext = "txt"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = _deliverables_dir() / f"{kind_norm}_{safe_subject}_{stamp}.{ext}"
        try:
            header = (
                f"To: {to or '-'}\nSubject: {subject or '-'}\n"
                f"Persona: {meta['name']} ({meta['title']})\n"
                f"Generated: {time.strftime('%Y-%m-%d %H:%M')}\n{'-' * 48}\n\n"
            )
            path.write_text(header + text + "\n", encoding="utf-8")
        except Exception as exc:
            return {"success": False, "error": f"Draft written but could not be saved: {exc}", "output": text}

        persona.log_interaction(meta["key"], "assistant", f"Drafted {kind_norm}: {subject or brief[:60]}")

        summary = f"{kind_norm.capitalize()} drafted in the '{meta['name']}' voice."
        if not used_llm and err:
            summary += f" (LLM unavailable, generated a structured draft: {err})"
        return {
            "success": True,
            "summary": summary,
            "output": text,
            "path": str(path),
            "persona": meta["key"],
            "used_llm": used_llm,
        }

    return {
        "success": False,
        "error": f"Unknown action '{action}'. Use set, get, list, remember, recall, draft or status.",
    }
