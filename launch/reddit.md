# Reddit Launch Posts

Post the **repo link + a GIF/video** (images convert far better than links).
Engage in comments. Don't cross-post the identical text — tailor per sub.

---

## r/LocalLLaMA

**Title:** I built a local-first JARVIS-style AI desktop assistant for Windows — voice, vision, 100+ tools, self-evolving (open source, source-available)

**Body:**
```
Hey everyone,

Spent a long time building Sudarshana Chakra — a single-window PyQt6 desktop
assistant for Windows. Unlike a chat wrapper, it plans and executes real desktop
actions.

Highlights:
- Real-time Gemini Live voice + multimodal screen vision
- Autonomous planner -> executor -> replan loop
- Self-evolving: forges new Python tools when it lacks a capability, sandbox-tests
  them, and hot-loads them (no restart)
- Self-healing: catches its own tracebacks and patches the faulty code
- 100+ tools: Playwright/CDP browser, Office docs, Spotify MCP, geospatial globe,
  hardware circuit vision, and 5 business verticals (inventory/procurement/
  finance/manufacturing/marketing)
- Local-first: state in %LOCALAPPDATA%\SudarshanaAI\, keys gitignored

It's source-available (commercial EULA, free for one personal install). Would love
feedback from this crowd on the self-evolution sandbox and the tool registry design.

Repo (with install + demo): https://github.com/SHIVAM73566/Sudarshana-Chakra

[ATTACH: 20–30s demo GIF]
```

---

## r/Python

**Title:** Sudarshana Chakra — a 190-file, zero-error-gated PyQt6 AI desktop agent (self-healing + self-evolving tool forge)

**Body:**
```
Sharing a large PyQt6 desktop project of mine, built with a strict "0 errors"
philosophy.

Engineering details this sub might enjoy:
- core/auto_deploy.py: a pre-flight gate — byte-compile all files, import every
  module in isolation, validate 55 dynamic tool schemas, audit for bare excepts,
  run the test suite. CI runs the same on Windows.
- core/router.py: classifies each goal into single-tool / DAG / self-evolution.
- SkillForge + SkillCrucible: LLM synthesizes a new tool, runs ast.parse + a
  sandboxed test, then dynamically registers it.
- Heavy work runs on daemon threads / executors so the Qt loop never blocks.
- All tool schemas normalized to {"type": "OBJECT", "properties": {...}}.

Everything is typed, additive, and import-guarded for optional deps.

Repo: https://github.com/SHIVAM73566/Sudarshana-Chakra

[ATTACH: demo GIF or a screenshot of the architecture diagram]
```

---

## r/SelfHosted

**Title:** Sudarshana Chakra — local-first Windows desktop AI agent (voice/vision, 100+ tools, no cloud dependency for local features)

**Body:**
```
For the local-first crowd: a Windows desktop AI assistant where memories, keys
and config stay local (%LOCALAPPDATA%\SudarshanaAI\). It runs and does all local
features with no API key at all — add a Gemini key only if you want live voice and
vision.

- Business verticals store data in a local encrypted SQLite DB
- Browser automation persists your real logged-in profile (no fresh sessions)
- Source available to inspect; single personal install

Repo + one-command install: https://github.com/SHIVAM73566/Sudarshana-Chakra

[ATTACH: demo GIF]
```

---

## r/artificial

**Title:** An AI assistant that rewrites its own tools when it hits a capability gap — here's Sudarshana Chakra

**Body:**
```
Most "AI assistants" answer; this one acts and adapts. Sudarshana Chakra runs an
autonomous loop on Windows: it plans, executes desktop actions, and — when it
doesn't have a tool for a task — writes a new Python tool itself, sandbox-tests
it, and loads it live. It also self-heals runtime crashes.

Demo in the repo. Curious what this crowd thinks about self-modifying agents in
consumer software.

https://github.com/SHIVAM73566/Sudarshana-Chakra
```

---

## r/windows

**Title:** Made a JARVIS-style AI assistant for Windows 10/11 (voice, screen vision, controls your PC)

**Body:**
```
Native Windows desktop app (PyQt6). Talk to it, show it your screen, and it
automates your PC — documents, browser, files, even hardware/circuit help.
Double-click installer: start_sudarshana.bat handles Python + deps for you.

Free to try (one personal install). Feedback welcome.

https://github.com/SHIVAM73566/Sudarshana-Chakra
[ATTACH: GIF of it opening apps / building a spreadsheet]
```

---

### Posting tips
- **r/LocalLLaMA & r/artificial** are the highest-signal for this project.
- Post with an **image/GIF as the main media**, link in the body (some subs auto-filter link-only posts).
- Read each sub's self-promo rules; use a flair if required.
- Post at ~8–11 AM US time on weekdays.
