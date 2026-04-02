# Parrrot 🦜

> **Your private Jarvis. Runs on your machine. Does anything.**

Parrrot is an open-source personal AI assistant that lives on your computer. It controls your PC, browses the web by actually opening your browser, watches YouTube videos, manages your files, sends notifications, and works autonomously in the background — all using a local AI model so nothing leaves your machine.

---

## Install

```bash
pip install parrrot
parrrot
```

That's it. The setup wizard handles everything else.

---

## What it does

| Capability | How |
|---|---|
| Full PC control | Mouse, keyboard, window management |
| Real browser automation | Opens Firefox/Chrome via Playwright |
| YouTube understanding | Extracts frames + transcript, summarizes |
| File management | Read, write, search, organize, zip |
| Desktop cleanup | One command sorts everything by type |
| Persistent memory | Stored locally as JSON in `~/.parrrot/` |
| Autonomous background mode | Runs 24/7, notifies you when needed |
| Skill system | Add new abilities with plain Python files |
| Advanced task execution | Auto-plans complex goals and executes step-by-step |
| Smart recovery | Escalates reasoning in hybrid mode after repeated tool failures |
| Beautiful terminal UI | Rich-powered chat and dashboard |
| Non-coder friendly | Setup wizard, plain-English errors |

---

## Quick demo

```
$ parrrot chat

╭─ Parrrot ─────────────────────────────────────────────────────────╮
│  Model: llama3.2 (local)  │  Memory: 47 facts  │  Type exit to quit │
╰────────────────────────────────────────────────────────────────────╯

You: clean my desktop

Parrrot: I can see 23 files on your desktop. Organizing them now...
  ↳ [tool: get_desktop_contents] Found 23 items
  ↳ [tool: clean_desktop] Creating folders...
  ✓ Moved 12 images → Images/, 8 docs → Documents/, 3 others → Misc/

You: summarize this YouTube video https://youtube.com/watch?v=...

Parrrot: Getting the video info and transcript...
  ↳ [tool: get_video_info] Title: "How to..."
  ↳ [tool: get_transcript] Fetched 4,200 chars
  ✓ This video is about...
```

---

## Commands

```bash
parrrot                    # First run → setup wizard, then → chat
parrrot chat               # Start talking to Parrrot
parrrot run "task"         # One-off task, then exit
parrrot daemon             # Run in background 24/7 (activates global hotkey)
parrrot stop               # Stop background daemon
parrrot status             # Show what Parrrot is doing
parrrot memory             # Browse what it remembers
parrrot memory forget "X"  # Delete a memory
parrrot config             # Edit config file
parrrot skills             # List installed skills
parrrot skills add file.py # Install a new skill
parrrot hotkey             # Register Win+Shift+P global hotkey (standalone)
parrrot update             # Update to latest version
```

## Navigation

Parrrot uses **prompt_toolkit** for a fast, keyboard-driven chat experience:

| Key | Action |
|-----|--------|
| `↑` / `↓` | Scroll through command history |
| `Ctrl+R` | Search history — type to filter past commands |
| `Tab` | Autocomplete slash commands |
| `Ctrl+L` | Clear screen |
| `Alt+F` / `Alt+B` | Jump word forward / backward |
| `Ctrl+C` | Cancel current input |
| `Win+Shift+P` | **Global hotkey** — open Parrrot from anywhere on your PC |

### Chat slash commands

| Command | Action |
|---------|--------|
| `/new` or `/reset` | Clear conversation, start fresh |
| `/status` | Show model, memory, and config info |
| `/model` | Show active model |
| `/verbose` | Toggle verbose tool output |
| `/compact` | Compress conversation to memory |
| `/memory [query]` | Search or browse memories |
| `/tools` | List all available tools |
| `/history` | Show recent command history |
| `/hotkey` | Show global hotkey info |
| `/clear` | Clear the screen |
| `/help` | Show all commands and keyboard shortcuts |

### Global hotkey

Run `parrrot daemon` in the background and press **Win+Shift+P** from anywhere on your PC to instantly open or focus the Parrrot chat window.

```bash
# One-time setup
pip install keyboard        # usually already included
parrrot daemon              # starts background daemon + registers hotkey
```

History is persisted to `~/.parrrot/history` so your past commands are always available across sessions.

---

## Privacy

Everything runs locally. Memory is stored in `~/.parrrot/` as plain JSON files you can read and edit. No telemetry. No cloud unless you configure it. Your AI, your machine, your data.

---

## Supported models

**Local (via Ollama — runs 100% on your machine):**
- llama3.2, mistral, phi3, gemma2, qwen2.5, deepseek-r1
- Any model from [ollama.com/library](https://ollama.com/library)

**Cloud (optional — you provide the API key):**
- Anthropic Claude (claude-sonnet-4-6, claude-haiku-4-5)
- OpenAI (gpt-4o, gpt-4o-mini)
- MiniMax (OpenAI-compatible; e.g. `kimi-k2.5` via MiniMax routing)
- Kimi (Moonshot) / `kimi` provider (OpenAI-compatible; e.g. `kimi-k2.5`)
- Google Gemini (gemini-1.5-pro)
- Groq (llama3-70b — fast and has a free tier)

**Hybrid:** Use local for private tasks, cloud for heavy tasks — Parrrot decides automatically.

---
### Configure Minimax / Kimi (cloud)
Set these in `~/.parrrot/config.toml`:
```
model.mode = "cloud"
model.cloud_provider = "minimax"   # or: "kimi"
model.cloud_model = "kimi-k2.5"   # example model name for Kimi
# model.cloud_endpoint = ""         # optional override (leave empty for defaults)
```
Provide API keys via env vars:
```
MINIMAX_API_KEY=...
KIMI_API_KEY=...
```

---

## Adding skills

Drop a `.py` file into `~/.parrrot/skills/`:


```python
# ~/.parrrot/skills/morning_briefing.py

SKILL_NAME = "Morning Briefing"
SKILL_DESCRIPTION = "Summarize emails and calendar every morning at 8am"
SCHEDULE = "0 8 * * *"  # cron expression

async def run(agent, memory, tools):
    result = await agent.run_task(
        "Summarize my unread emails and today's calendar. "
        "Send a desktop notification with the highlights."
    )
```

Restart the daemon (`parrrot daemon`) to activate.

---

## Optional dependencies

```bash
# Browser automation (web search, form filling)
pip install playwright && playwright install

# OCR (read text from screen)
pip install pytesseract Pillow
# Also install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki

# YouTube understanding
pip install yt-dlp

# Voice input/output
pip install pyttsx3 SpeechRecognition

# Install everything at once:
pip install parrrot[all]
```

---

## Project structure

```
parrrot/
├── parrrot/
│   ├── main.py          CLI entry point (Typer)
│   ├── onboarding.py    First-run setup wizard (Rich)
│   ├── config.py        Config loader/saver (TOML)
│   ├── core/
│   │   ├── agent.py     Main reasoning loop
│   │   ├── memory.py    JSON memory system
│   │   ├── router.py    Local/cloud LLM router
│   │   ├── context.py   System prompt builder
│   │   └── scheduler.py Background task scheduler
│   ├── models/
│   │   ├── ollama_local.py   Ollama local backend
│   │   └── ollama_cloud.py   Cloud API backend
│   ├── tools/
│   │   ├── filesystem.py
│   │   ├── shell.py
│   │   ├── browser.py
│   │   ├── screen.py
│   │   ├── pc_control.py
│   │   ├── youtube.py
│   │   ├── email_tool.py
│   │   ├── calendar_tool.py
│   │   ├── system_info.py
│   │   └── notifications.py
│   ├── skills/          User Python skill files
│   └── ui/
│       ├── chat.py      Interactive chat
│       └── dashboard.py Status dashboard
└── pyproject.toml
```

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Built with Python, Rich, Typer, Ollama, Playwright, and a lot of ❤️.
