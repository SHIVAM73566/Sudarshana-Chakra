# Changelog

All notable changes to **Sudarshana Chakra** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Documentation: one-command Quick Install, beginner-friendly Easy Installation Guide, SEO taglines and social badges.

## [1.0.0] — 2026-10-21

The first commercial-ready release of Sudarshana Chakra — a self-evolving,
multimodal personal AI desktop environment for Windows.

### Added
- **Autonomous Deep Research** (`core/deep_research.py`) — decomposes a goal,
  gathers live web + local-document evidence, synthesizes a step-by-step
  strategy, and can hand off to SkillForge to forge a brand-new tool.
- **Enterprise Business Verticals** (`core/business/`) — five fully wired tools:
  `inventory_manager`, `procurement_manager`, `finance_manager`,
  `manufacturing_manager`, `marketing_manager`, backed by a thread-safe SQLite
  store with at-rest encryption and Excel/CSV export.
- **Unified Tool Registry** (`core/tool_registry.py`) — 100+ tools aggregated
  from builtins, business verticals, dynamic features and custom tools behind a
  single facade.
- **Multi-provider licensing engine** — Lemon Squeezy / Payhip / Gumroad /
  offline-RSA drivers with automatic key-shape detection, hardware binding and a
  clock-rollback guard (`core/license_providers.py`, `core/license_guard.py`,
  `core/license_ui.py`).
- **Workspace profile switcher** (CEO / CTO / SME / Personal) in Settings.
- **Unlockable avatar system** — image, animated and 3D companion avatars.
- **Named themes** with live switching.
- **Persistent self-healing** — permanent error boundaries + self-improvement
  interceptor.
- **Playwright MCP client** (`browser_mcp` tool) and **PPT template workflow**
  (`ppt_template` tool) wired into the registry.
- **Remote access gateway** (`sudarshana_connect/gateway/`) — websocket bridge
  with authentication, pairing, device management and command routing on `:8765`.
- **CI quality gate** (`core/auto_deploy.py`) — compile, import, schema, hygiene
  and test pre-flight; plus a GitHub Actions workflow.

### Changed
- PDF text extraction now uses `pypdf` as the primary backend with optional
  fallbacks.
- Removed a shadowed duplicate `set_speech_sink` and dead imports; corrected the
  documented Python version.

### Fixed
- Repaired the dead attach pipeline and missing hardware widgets.
- Normalized all tool registry schemas to `{"type": "OBJECT", "properties": {}}`.
- Made dynamic skill loading deterministic.
- Fixed a shadowing re-import in `workspace_store.py`.

### Security
- Sanitized `app_settings` to portable defaults; zero hardcoded user paths.
- Secret scan is clean; `.env` and `api_keys.json` are gitignored.
- Anti-tamper manifest signing for guarded core files.

---

[Unreleased]: https://github.com/SHIVAM73566/Sudarshana-Chakra/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/SHIVAM73566/Sudarshana-Chakra/releases/tag/v1.0.0
