# Hacker News — "Show HN" Launch Post

**Best time to post:** Tuesday–Thursday, ~8:00–10:00 AM US Pacific (15:00–17:00 UTC).
Be present in the comments for the first 2–3 hours. Reply fast and honestly.

---

## Title (choose one — keep it literal, HN dislikes hype)

```
Show HN: Sudarshana Chakra – open JARVIS-style AI assistant for Windows
```

```
Show HN: A self-evolving, voice+vision AI desktop assistant for Windows (100+ tools)
```

```
Show HN: Sudarshana Chakra – local-first AI agent that actually controls your PC
```

---

## Body

```
Hi HN,

I built Sudarshana Chakra, a single-window PyQt6 desktop assistant for Windows
that behaves like a JARVIS workstation. It talks (real-time Gemini Live audio),
sees your screen (multimodal vision), and actually executes desktop actions
instead of just answering questions.

A few things that make it more than a chat wrapper:

- Autonomous agent loop: planner -> executor -> replan. It routes a goal through
  a classifier (single-tool vs DAG vs self-evolution) and runs the right path.
- Self-evolving: when it lacks a capability it synthesizes a new Python tool
  into features/, tests it in an isolated sandbox ("Crucible"), and hot-loads it
  with no restart.
- Self-healing: a background sentry catches tracebacks, asks an LLM for a root
  cause + patch, validates the AST, and rolls back if the repair doesn't land.
- 100+ built-in tools behind one registry: browser automation (Playwright/CDP),
  Office docs (Excel/Word/PPT/PDF), geospatial/globe, Spotify MCP, hardware
  circuit vision, plus five business verticals (inventory, procurement, finance,
  manufacturing, marketing) on a local encrypted SQLite store.
- Local-first: keys, memories and config live in %LOCALAPPDATA%\SudarshanaAI\;
  nothing is uploaded except what you explicitly send to your chosen provider.
- Zero-error quality gate (core/auto_deploy.py): compile + import + schema +
  hygiene + tests before any release; CI runs the same on every push.

It's a commercial source-available EULA (run for one personal install, inspect
the source), free of charge to try. Windows 10/11, Python 3.11+.

Repo: https://github.com/SHIVAM73566/Sudarshana-Chakra

Happy to answer anything about the architecture, the self-evolution sandbox, or
how the async model keeps the Qt event loop responsive.
```

---

## Anticipated comments (have answers ready)

- **"How is this different from AutoGPT/Open Interpreter?"** → Ask HN-ready answer: single-window native desktop app (not CLI/loop), PyQt6 UI with live voice, self-evolution sandbox, 5 business verticals, Windows UI Automation first (not just coords/OCR).
- **"Security? It runs arbitrary code."** → AST validation, isolated Crucible sandbox, permission sentries, path-traversal guards, prompt-injection sanitization, grace-period anti-tamper. Honest caveat: still a powerful tool—run on a machine you own.
- **"Windows only?"** → Yes, deliberately (UI Automation/COM/pywin32 focus). Cross-platform is not on the roadmap.
