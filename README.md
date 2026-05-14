# 🤖 JARVIS AI Assistant

**Just A Rather Very Intelligent System**  
A voice-first AI assistant for Windows powered by local audio processing, Groq ultra-fast inference, and real-time voice interaction.

JARVIS can talk naturally, execute actions, browse the web, automate workflows, remember context, manage tasks, and assist with development through conversational commands.

---

## ⚡ Core Capabilities (Current MVP)

- Real-time text and voice interaction (browser speech APIs)
- WebSocket-based low-latency assistant loop
- Groq OpenAI-compatible inference integration (with local fallback)
- Local-first SQLite memory + FTS5 search
- Intent-based action routing
- Browser action commands
- Research command support
- Task creation and listing
- Multi-step plan and workflow execution
- Audio-reactive Three.js orb visualization
- Extensible multi-agent style module architecture

---

## 🧠 What JARVIS Can Do (Implemented Commands)

Use these from the UI input or voice:

- `remember <text>` → store memory
- `recall <query>` → semantic memory lookup
- `research <topic>` → web research summary fetch
- `open <url>` → browser automation intent
- `task <title>` → create a task
- `list tasks` → list tasks
- `system info` → OS capability check
- `run <command>` → execute shell command (**disabled by default**)

---

## �� System Architecture

```text
Microphone/Input
      ↓
Speech Recognition (browser)
      ↓
WebSocket Communication Layer
      ↓
FastAPI Core Server
      ↓
Groq AI Inference Engine (or local fallback)
      ↓
Intent Classification & Action Router
      ↓
┌──────────────────────────────┐
│ Browser Agent                │
│ Desktop Automation Engine    │
│ Workflow Executor            │
│ Research Engine              │
│ Memory System                │
└──────────────────────────────┘
      ↓
Response Generation
      ↓
Text-to-Speech (browser)
      ↓
Audio + UI Visualization
```

---

## ⚙️ Tech Stack

### Backend
- Python
- FastAPI
- WebSockets
- AsyncIO
- SQLite + FTS5

### AI
- Groq API (OpenAI-compatible endpoint)
- Pluggable provider design for future Claude/OpenAI integration

### Frontend
- Vite
- TypeScript
- Three.js

---

## 📂 Project Structure

```text
JARVIS/
├── backend/
│   ├── server.py
│   ├── actions.py
│   ├── browser_agent.py
│   ├── desktop_agent.py
│   ├── memory.py
│   ├── planner.py
│   ├── workflow_engine.py
│   ├── research_engine.py
│   ├── audio.py
│   ├── websocket_manager.py
│   └── task_manager.py
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── voice.ts
│   │   ├── orb.ts
│   │   ├── websocket.ts
│   │   └── ui.ts
│   └── package.json
├── database/
├── assets/
│   ├── audio/
│   └── models/
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Quick Start

### 1) Clone
```bash
git clone https://github.com/0xCyberMind/Jarvis.git
cd Jarvis
```

### 2) Backend Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Set your `.env`:
```env
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
OPENAI_API_KEY=
USER_NAME=YourName
ALLOW_SHELL_ACTIONS=false
CORS_ORIGINS=http://localhost:5173
```

### 3) Frontend Setup
```bash
cd frontend
npm install
cd ..
```

Optional frontend websocket override:
```bash
# frontend/.env
VITE_WS_URL=ws://localhost:8000/ws
```

### 4) Run Backend
```bash
python backend/server.py
```

### 5) Run Frontend
```bash
cd frontend
npm run dev
```

### 6) Open App
- http://localhost:5173

---

## 🔐 Safety Notes

- Shell execution is disabled by default (`ALLOW_SHELL_ACTIONS=false`).
- Dangerous command patterns are blocked.
- Desktop automation is Windows-gated in current MVP.

---

## 🛠 Planned Upgrades

- Wake-word engine and dedicated local STT/TTS pipeline
- Full browser automation flows with Playwright/Selenium integration
- Windows-native desktop control via Win32/PyAutoGUI
- Background notification and reminder scheduler
- Code execution sandboxing and stronger policy controls
- Offline local LLM and multi-device synchronization

---

## 🎯 Goal

Build a real-time autonomous AI operating assistant for Windows capable of voice interaction, automation, browser control, coding support, workflow execution, and intelligent task management.
