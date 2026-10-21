# FAQ

## General

### What is Sudarshana Chakra?
A self-evolving, multimodal, JARVIS-style AI assistant for Windows that can talk,
see your screen, and autonomously control your desktop.

### Is it free?
The source is available to inspect and run for a single personal installation.
See [LICENSE](../LICENSE) for the full commercial EULA. You can support the
project by [starring the repo](https://github.com/SHIVAM73566/Sudarshana-Chakra/stargazers).

### Do I need an API key?
No — Sudarshana launches and runs all local features without one. A free
[Google AI Studio](https://aistudio.google.com/app/apikey) Gemini key unlocks
real-time voice and vision.

## Installation

### The `start_sudarshana.bat` window closes immediately.
Run `python main.py` in a terminal to see the error, and check `logs\crash_*.log`.
See the [troubleshooting table](../README.md#-troubleshooting).

### `python` / `git` is not recognized.
Use the double-click installer (`start_sudarshana.bat`) which installs Python for
you, or install [Git for Windows](https://git-scm.com/download/win).

### Do I need Node.js?
Only for the Spotify MCP server. `bootstrap.ps1` installs it automatically.

## Usage

### Is my data sent to the cloud?
Only what you explicitly send to your chosen AI provider. Memories, keys and
config stay local in `%LOCALAPPDATA%\SudarshanaAI\`.

### Can I add my own tools?
Yes. Drop a module with `FEATURE_METADATA` + `execute(**kwargs)` into `features/`
or wire it through `agent/executor.py`; the registry hot-loads it. The assistant
can also forge new tools itself via SkillForge.

## Contributing

See [CONTRIBUTING](../CONTRIBUTING.md). Please run the quality gate
(`python core/auto_deploy.py`) before opening a PR.
