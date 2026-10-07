# ⚡ Sudarshana Chakra — Autonomous Desktop Operating Intelligence

<div align="center">

<img src="assets/sudarshana_chakra_logo_core.png" alt="Sudarshana Chakra Logo" width="420" />

### *The Self-Evolving, Multimodal Personal AI Desktop Environment*

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6%20%2B%20WebEngine-darkgreen?logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![Gemini 2.5](https://img.shields.io/badge/Model-Gemini%202.5%20Flash%20Native%20Audio-orange?logo=google&logoColor=white)](https://ai.google.dev/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6?logo=windows&logoColor=white)](https://microsoft.com/windows)

</div>

---

## 🌌 Overview

**Sudarshana Chakra** is a next-generation desktop intelligence built to function like an authentic JARVIS workstation. Combining real-time bi-directional native voice audio, multimodal computer vision, autonomous code self-evolution, and local system orchestrations, Sudarshana Chakra transforms your Windows PC into a self-evolving command center.

---

## ⚡ What's New in Sudarshana Chakra

### 1. 🔌 Holographic Hardware Assembler & Circuit HUD
- **Screen & Voice Part Recognition**: Sudarshana scans your screen via computer vision or parses voice commands (`"Sudarshana, how to connect DHT11 to Arduino Pro Mini"`) to recognize microcontrollers (Arduino Uno, Pro Mini, ESP32), sensors (DHT11, HC-SR04 ultrasonic, servos), and passive components.
- **In-App Interactive Pop-up**: Opens a compact, dark glassmorphic popup overlay directly inside Sudarshana showing:
  - Component cards with pinout labels (`VCC`, `DATA`, `GND`, `2`, `p8`, `p9`).
  - **Animated glowing neon SVG wires** with real-time flowing white electron pulse dots.
  - Numbered pin bubbles (`①`, `②`, `③`, `④`, `⑤`).
  - Operating voltage safety callouts and ready-to-flash Arduino C++ firmware.

### 2. 🧬 Project Ultron — Self-Evolving Autonomous Skill Crucible
- **On-the-Fly Code Synthesis**: When asked to execute a task outside its built-in toolkit, Sudarshana identifies the capability gap, writes a brand-new Python tool directly into `features/`, tests it inside an isolated sandbox ("The Crucible"), and auto-registers it dynamically without restarting the application.
- **Persistent Vault**: All forged skills are saved in your `features/` directory and hot-reloaded automatically.

### 3. 🛡️ Proactive Auto-Heal Engine
- **Self-Repairing Codebase**: Background sentry catches runtime exceptions, analyzes tracebacks using LLM root-cause reasoning, applies dynamic patches to the faulty code, and presents an interactive HUD repair telemetry card without crashing the assistant.

### 4. 🌊 Real-Time FFT Audio Waveform & Dynamic Glow Core
- **Live Physical Frequency Spectrum**: 9-bar reactive audio visualizer embedded directly into the Command Bar.
- **Dynamic State Glow States**:
  - 🟡 **Gold**: Standby / Listening
  - 🔵 **Cyan / Blue**: Capturing Voice (Live Energy Wave)
  - 🟣 **Purple**: Sudarshana Reasoning / Thinking
  - 🟢 **Green**: Executing Tool / System Action
  - 🔴 **Red**: Muted

### 5. 🧩 Visual Chain-of-Thought Execution Tracker
- **Agentic Step-by-Step HUD Cards**: Collapsible execution traces embedded directly into chat bubbles.
- Features sub-second execution latency chips (`[180ms]`, `[120ms]`), status badges (`COMPLETED`), and expandable `[Inspect]` drawers for parameters and raw JSON payloads.

### 6. 🌐 Interactive 3D HoloGlobe & Geospatial Radar
- **3D Earth & 2D Street Mapping**: WebGL spherical Earth globe with live great-circle flight routes, real-time aircraft radar tracking, turn-by-turn highway driving routes, and nearby POI scans (hospitals, fuel, ATMs).

### 7. 🎵 Official Spotify MCP Server Integration
- Built on the open **Model Context Protocol (MCP)** for robust, reliable music playback, album/artist searches, queue control, volume adjustment, and active device handover between PC and mobile.

### 8. ⚙️ Centralized API Setup Hub
- Complete Settings UI featuring dedicated cards for every connected service:
  - Google Gemini API (Live Voice & Vision)
  - Spotify MCP (Client ID & Client Secret)
  - OpenRouter / Anthropic
  - Weather & Radar APIs
  - Instagram & Smart Home
  - Instant live test-connection buttons.

### 9. 🔐 Voice Biometric Authorization Gate
- **Enrol once, lock your voice:** register a spoken pass-phrase (`"register voice password <phrase>"`). When the lock is engaged, only utterances carrying the voice password are accepted.
- **Unrecognised voice is refused:** unauthorised voice input is answered with *"Voice authorization is enabled. Please provide the voice password."*
- **Text master-password fallback:** set a secondary *text* password (`"set master password <password>"`) so you can unlock with the keyboard when no microphone is available. It unlocks the same session and never creates a bypass.
- **Dashboard toggle:** the web dashboard shows a `LOCK STATE` control (top bar) and the companion HUD displays a live `LOCK STATE: SECURE 🔒` badge; toggling either engages/disengages the same system-wide lock.
- **Safe fallback:** typed text input always remains available, so you are never locked out.
- Commands: `register voice password …`, `lock voice for security reasons`, `voice password is …`, `set master password …`, `master password is …`, `disable voice security`, `voice security status`, `forget voice password`.
- State is stored locally at `%LOCALAPPDATA%\SudarshanaAI\config\voice_security.json` (never bundled in releases).

### 10. 🪪 Immutable Brand, Logo, Avatar & Companion HUD
- **Tamper-proof identity:** the application name `Sudarshana Chakra` and codename `SudarshanaChakra` are frozen at boot (`core/brand.py`); any attempt to alter them aborts startup.
- **Locked brand logo:** the primary logo `assets/sudarshana_chakra_logo_core.png` (plus the square `assets/app_icon_core.png` and browser `assets/favicon.ico`) is embedded as a Base64 constant, self-heals if deleted or modified, is verified against its SHA-256 fingerprint at boot (`core/brand_logo.py`), and is written read-only. There is no setting, dashboard control or UI property to rename, override or delete it; any config/env attempt to point the logo elsewhere is treated as a brand-integrity violation.
- **Permanent guardian avatar:** the companion portrait `assets/sudarshana_avatar_core.png` is embedded as a Base64 constant, self-heals if deleted or modified, and is re-verified against its SHA-256 fingerprint (`core/avatar.py`). It is rendered inside a glowing, non-removable circular HUD (rotating telemetry rings, scanlines, live gauges) in the centre-left of the dashboard, carrying the badges **SUDARSHANA COMPANION — ACTIVE**, **BIOMETRIC SYNC** and **LOCK STATE: SECURE 🔒**. The image cannot be swapped, overlaid or deleted; only the textual display name is user-changeable.
- **Installing/refreshing the official logo:**

  ```powershell
  python tools/set_brand_logo.py --source path/to/sudarshana_chakra_logo.png
  ```

  This writes the read-only assets, regenerates `core/brand_logo_asset.py` (embedded copies + SHA-256), and rebuilds the 16:9 banner and square icon.

---

## 🛠️ Core Capabilities

### 🎙️ Multimodal Native Audio & Vision
- Sub-500ms low-latency conversation via Gemini 2.5 Flash Native Audio.
- Live webcam and desktop screen vision for real-time document analysis, code debugging, and hardware component recognition.

### 🖥️ Deep Windows Desktop Orchestration
- **Application & Process Manager**: Launch, control, inspect, and freeze memory-heavy background processes.
- **System Settings**: Toggle Wi-Fi, adjust volume, screen brightness, dark/light themes, and monitor CPU/RAM/Battery metrics.
- **Smart Window Control**: Minimize, maximize, tile, or arrange windows across multi-monitor setups.
- **Clipboard Sentry**: Instant analysis, translation, formatting, or debugging of copied text/code.

### 📄 Autonomous Office & Document Architect
- **Word (`.docx`)**: Generate formatted professional documents, reports, and resumes.
- **Excel (`.xlsx`)**: Create complex multi-sheet workbooks with formulas, charts, and financial models.
- **PowerPoint (`.pptx`)**: Build branded presentations with slide layouts, typography, and speaker notes.
- **PDF Suite**: Convert, merge, extract, and assemble PDF deliverables.

### 📱 Sudarshana Connect (Android Companion)
- **AI Phone Call Proxy**: Sudarshana screens incoming phone calls, talks to the caller, takes meeting notes, and delivers immediate desktop transcripts and summaries.
- **Ecosystem Sync**: Device geolocation, SMS notifications, and battery status.

### 🏡 Smart Home Hub
- Control smart lights, smart plugs, AC units, fans, and televisions with direct Tuya and Home Assistant integrations.

### 🧠 Long-Term Memory & Identity
- Adaptive memory engine stores personal user preferences, ongoing projects, and custom instructions across sessions.

---

## 🚀 Quick Start

### Prerequisites
- **Windows 10 / 11** (64-bit)
- **Python 3.11** or **Python 3.12**
- **Git**
- Working Microphone & Speakers (Webcam optional for vision)
- **Google Gemini API Key** (Get from [Google AI Studio](https://aistudio.google.com/))

### Installation

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/SHIVAM73566/Sudarshana-Chakra.git
   cd Sudarshana-Chakra
   ```

2. **Run the Automated Setup:**
   ```powershell
   python setup.py
   ```
   *Or launch using the included batch file:*
   ```cmd
   start_sudarshana.bat
   ```

3. **Configure API Keys:**
   - **Option A — `.env` file (recommended for first install):** copy `.env.example` to `.env` and fill in your keys:
     ```ini
     GEMINI_API_KEY=your_gemini_api_key
     NVIDIA_API_KEY=nvapi-your_nvidia_api_key
     OPENROUTER_API_KEY=            # optional
     ```
     Sudarshana loads `.env` at boot and **degrades gracefully**: if a key is missing it falls back to the next configured provider, and local/text features keep working without any key.
   - **Option B — in-app Settings:** launch Sudarshana Chakra, open the **Settings** panel, and enter keys per provider (Google Gemini, NVIDIA, OpenRouter). Provider values are stored locally in `%LOCALAPPDATA%\SudarshanaAI\config\api_keys.json`.
   - Choosing the active provider: set **Default AI Provider** to `Google Gemini` or `NVIDIA` (NVIDIA NIM is a drop-in text backend). Gemini is used for Live voice/vision.

### 🔑 API Keys (NVIDIA / Gemini)

| Provider | Where to get a key | Used for | Required? |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | [Google AI Studio](https://aistudio.google.com/app/apikey) | Live voice, vision, text fallback, summarisation | Yes for voice |
| **NVIDIA NIM** (`nvapi-…`) | [build.nvidia.com](https://build.nvidia.com) | Text planning/execution when set as default provider | Optional |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | Legacy/fallback text provider | Optional |

---

## 🔐 Enabling the Voice Biometric Lock

1. Say or type: **`register voice password <your secret phrase>`** — this enrols the pass-phrase and enables the lock.
2. Lock at any time with **`lock voice for security reasons`** (or click the **BIOMETRIC** toggle on the mobile Dashboard).
3. Any voice command that does not carry the pass-phrase is refused with *"Voice authorization is enabled. Please provide the voice password."*
4. If no microphone is available, **type a secondary master password** (set once with `set master password <secret>`) using `master password is <secret>`.
5. Release with **`disable voice security`**, or wipe with **`forget voice password`**.

---

## 🎮 Voice & Command Cheat Sheet

| Intent | Sample Voice / Text Command |
| :--- | :--- |
| **Hardware Circuit** | *"Sudarshana, how to connect DHT11 to Arduino Pro Mini"* |
| **Circuit Vision** | *"See the Arduino parts on my screen and tell me how to assemble them"* |
| **Self-Evolution** | *"Sudarshana, learn a new skill to track International Space Station coordinates"* |
| **Flight Radar** | *"Show flight route from Mumbai to London"* |
| **Nearby Amenities** | *"Find nearby hospitals on the map"* |
| **Music Playback** | *"Play Starboy on Spotify"* |
| **Phone Screening** | *"Screen this incoming call for me"* |
| **Office Documents** | *"Create a project roadmap spreadsheet in Excel"* |
| **System Health** | *"Check system resources and kill heavy apps"* |

---

## 🏗️ Architecture

```
Sudarshana Chakra/
├── main.py                     # Main application entry point & live event loop
├── ui.py                       # PyQt6 GUI: Command Bar, Waveform FFT, HUD Wings, Chat
├── actions/                    # Built-in action tools & executors
│   ├── circuit_assembler.py    # Hardware vision & circuit solver engine
│   ├── spotify_controller.py   # Spotify MCP client & playback manager
│   ├── geospatial_globe.py     # Great-circle routes, radar & POI fetcher
│   ├── auto_heal_engine.py     # Proactive exception interceptor & patcher
│   ├── call_assistant.py       # Android phone call proxy & transcript analyzer
│   └── office_builder.py       # Excel, Word, PPTX & PDF generators
├── core/                       # Core system architecture
│   ├── circuit_hud.py          # Compact in-app holographic circuit popup overlay
│   ├── globe_window.py         # 3D WebGL Earth globe & map controller
│   ├── skill_forge.py          # Project Ultron: LLM skill synthesizer
│   ├── skill_crucible.py       # Isolated test execution sandbox
│   ├── dynamic_registry.py     # Runtime tool hot-reloader & dispatcher
│   └── identity.py             # System prompt & behavioral core
├── features/                   # Self-evolved & custom Python tools
│   ├── circuit_schematic.py    # Modular circuit schematic feature
│   └── spotify_mcp.py          # Modular Spotify feature
├── smart_home/                 # Smart device provider & discovery services
└── sudarshana-connect-android/     # Companion Android mobile application
```

---

## 🔒 Security & Privacy

- All long-term memories, credentials, and configuration files are stored locally in `%LOCALAPPDATA%\SudarshanaAI\`.
- External tools run through permission sentries and the isolated Crucible sandbox.
- Audio and video frames are only streamed during active conversation sessions.

---

## 📦 Building a Release Package

Create a clean, distributable ZIP (source, assets, launchers and installer specs — no virtual environment, git metadata, caches, secrets, or personal runtime config):

```powershell
python package_release.py
```

The archive is written to `dist/Sudarshana_Chakra_AI_v<version>.zip`.

---

## 📄 License

**Personal & Private Local Use Only — No Distribution.**

This project is licensed under the **Sudarshana Chakra Source-Available Personal Use License**.

- ✅ **Allowed:** You may download, clone, inspect, build, and run the software locally strictly on your own personal device for private, personal, educational, and research use.
- 🚫 **Strictly Prohibited (No Distribution):** You may **NOT** distribute, redistribute, re-upload, mirror, share, transmit, sublicense, or publish this software, repository, binaries, or derivative works anywhere (including other Git hosts, public repositories, or cloud platforms). The only official distribution source is this repository.
- 🚫 **Strictly Prohibited (No Commercial Use):** You may **NOT** sell, rent, monetize, bundle, commercialize, or host this software as a paid SaaS/cloud service.

For full terms and legal conditions, see the [LICENSE](LICENSE) file. For commercial licensing inquiries, reach out via [Discord](https://discord.gg/gEYmJKKtq3).

<div align="center">
<b>Sudarshana Chakra</b> • Built with intelligence, precision, and autonomy.
</div>
