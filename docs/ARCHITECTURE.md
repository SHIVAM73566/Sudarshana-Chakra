# Architecture

Sudarshana Chakra is a single-window PyQt6 desktop application built around an
autonomous agent loop with a large, extensible tool registry.

## High-Level Flow

```
        ┌──────────────────────────────────────────────────────────┐
        │                    UI  (ui.py · PyQt6)                   │
        │   Command bar · FFT waveform · HoloCore · chat · HUD      │
        └───────────────┬──────────────────────────────────────────┘
                        │  user intent (voice / typed)
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │              Agent Loop  (main.py · agent/)              │
        │   planner → executor → replan                            │
        └───────┬───────────────────────┬──────────────────────────┘
                │                       │
                ▼                       ▼
     ┌──────────────────┐    ┌──────────────────────────────────┐
     │  core/router.py  │    │   agent/executor.py  _call_tool   │
     │  goal classify   │    │   dispatch to 100+ tools          │
     │  evolution|tool| │    └───────┬──────────────────────────┘
     │  dag             │            │
     └────────┬─────────┘            ▼
              │            ┌──────────────────────────────────┐
              │            │     core/tool_registry.py         │
              │            │  builtins + business + dynamic    │
              ▼            └───────┬──────────────────────────┘
     ┌──────────────────┐          │
     │  SkillForge /    │          ▼
     │  SkillCrucible   │   ┌──────────────────────────────────┐
     │  (self-evolve)   │   │  actions/ · core/business/ ·      │
     └──────────────────┘   │  services/ · features/            │
                            └──────────────────────────────────┘
```

## Core Subsystems

| Subsystem | Location | Responsibility |
| :--- | :--- | :--- |
| UI | `ui.py` | Single-window PyQt6 interface, themes, workspace profiles |
| Agent loop | `main.py`, `agent/` | Planning, execution, replanning, task queue |
| Router | `core/router.py` | Classifies goals → evolution / single-tool / DAG |
| Tool registry | `core/tool_registry.py` | Unified facade over builtins + verticals + dynamic tools |
| Business verticals | `core/business/` | Inventory, procurement, finance, manufacturing, marketing |
| Deep research | `core/deep_research.py` | Decompose → evidence → strategy → forge |
| Self-evolution | `core/skill_forge.py`, `core/skill_crucible.py` | Synthesize + sandbox-test new tools |
| Self-healing | `core/self_improvement.py`, `core/error_boundary.py` | Intercept tracebacks, repair, roll back |
| Licensing | `core/license_guard.py`, `core/license_providers.py` | Multi-provider, hardware-bound, offline fallback |
| Remote gateway | `sudarshana_connect/gateway/` | WebSocket bridge on `:8765` |
| Quality gate | `core/auto_deploy.py` | Compile + imports + schema + hygiene + tests |

## Data & Privacy

- All runtime state lives in `%LOCALAPPDATA%\SudarshanaAI\` (config, memories,
  business DB, research cache, licenses).
- Secrets are read from `.env` / `api_keys.json` (gitignored) and never logged.
- External/tool inputs are treated as untrusted (prompt-injection defense).

## Async Model

Heavy work never blocks the Qt event loop: tasks run on daemon threads,
`ThreadPoolExecutor`, or the `agent/task_queue.py` worker pool.
