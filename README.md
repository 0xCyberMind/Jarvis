# JARVIS

<div align="center">

# Just A Rather Very Intelligent System

### **The AI Operating System for Your Computer**

Voice-first AI assistant that can talk, reason, automate your workflow, browse the web, manage your schedule, remember context, and build software using natural language.

<p>
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white">
<img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white">
<img src="https://img.shields.io/badge/React-Frontend-61DAFB?style=for-the-badge&logo=react&logoColor=black">
<img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white">
<img src="https://img.shields.io/badge/Ollama-Local_AI-black?style=for-the-badge">
<img src="https://img.shields.io/badge/OpenAI-Supported-412991?style=for-the-badge">
<img src="https://img.shields.io/badge/Groq-Supported-F55036?style=for-the-badge">
</p>

> **"Will do, sir."**

*Inspired by the cinematic AI assistant experience while designed for real-world productivity.*

</div>

---

# ✨ Features

- 🎙️ Natural voice conversations
- 🧠 Persistent long-term memory
- 💻 AI software generation with Claude Code
- 🌐 Web browsing & research
- 📅 Apple Calendar integration
- 📧 Apple Mail (read-only)
- 📝 Apple Notes
- 📋 Task planning
- ⚡ Browser automation
- 🔍 Context-aware assistance
- 🎨 Audio-reactive Three.js orb
- 🔒 Local-first architecture

---

# 🚀 Demo

Replace these placeholders:

```text
docs/demo.gif
docs/screenshots/home.png
docs/screenshots/orb.png
```

---

# 🏗 Architecture

```text
Microphone
      │
      ▼
Speech Recognition
      │
      ▼
 FastAPI Server
      │
 ┌────┴────┐
 │ Planner │
 │ Memory  │
 │ Actions │
 └────┬────┘
      ▼
    LLM Layer
(Ollama/OpenAI/Groq)
      │
      ▼
 Tool Router
      │
 ┌────┼────────────┐
 ▼    ▼      ▼    ▼
Mail Calendar Notes Browser
      │
      ▼
 Browser TTS
      │
      ▼
 Speaker + Orb
```

# 📦 Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python |
| Frontend | React + TypeScript + Vite |
| Graphics | Three.js |
| Memory | SQLite FTS5 |
| Browser | Playwright |
| AI | Ollama / OpenAI / Groq |
| Communication | WebSocket |
| Voice | Web Speech API |

---

# ⚡ Quick Start

```bash
git clone https://github.com/yourusername/jarvis.git
cd jarvis

cp .env.example .env

pip install -r requirements.txt

cd frontend
npm install
cd ..

python server.py

cd frontend
npm run dev
```

Open:

http://localhost:5173

---

# ⚙ Configuration

```env
LLM_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini

OPENAI_API_KEY=

GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant

USER_NAME=Tony
```

---

# 📁 Project Structure

```text
jarvis/
│
├── frontend/
├── memory.py
├── actions.py
├── browser.py
├── planner.py
├── work_mode.py
├── server.py
├── calendar_access.py
├── notes_access.py
├── mail_access.py
├── docs/
└── README.md
```

---

# 🎯 Example Commands

- Build me a SaaS landing page
- Search latest AI news
- Open YouTube
- What's on my calendar today?
- Save this as a note
- Remember I prefer React
- Summarize unread emails
- Plan my day
- Research Tesla
- Explain this code

---

# 🔥 Feature Status

| Feature | Status |
|----------|--------|
| Voice Assistant | ✅ |
| Memory | ✅ |
| Calendar | ✅ |
| Notes | ✅ |
| Mail | ✅ |
| Browser Automation | ✅ |
| Claude Code | ✅ |
| Research | ✅ |
| Planning | ✅ |

---

# 🔒 Security

- Local-first by default
- Read-only Mail integration
- API keys remain local
- Secure WebSocket
- No mandatory cloud dependency

---

# 📊 Performance

| Metric | Typical |
|---------|----------|
| Voice Response | <700ms |
| Memory Search | <20ms |
| WebSocket | Real-time |
| Local AI | Supported |

---

# 🛣 Roadmap

## v1
- Voice Assistant
- Memory
- Calendar
- Notes
- Browser

## v2
- Linux Support
- Windows Support
- Docker
- MCP
- Plugins

## v3
- Mobile App
- Vision
- Offline Wake Word
- Multi-Agent Collaboration

---

# 🤝 Contributing

1. Fork
2. Create feature branch
3. Commit
4. Push
5. Open Pull Request

---

# ❓ FAQ

**Does it work offline?**

Yes, with Ollama.

**Can I use OpenAI?**

Yes.

**Can I use Groq?**

Yes.

**Windows support?**

Planned.

---

# 📜 License

Free for personal, non-commercial use.

Commercial licensing available.

---

# ❤️ Credits

Built by Bhaskar .

Inspired by the legendary AI assistant from the Marvel universe.

This project is an independent fan project and is not affiliated with Marvel Entertainment or The Walt Disney Company.
