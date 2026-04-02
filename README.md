# Parrrot — Developer Documentation

> Your private Jarvis. Runs on your machine. Does anything.

---

## Table of Contents

1. [What is Parrrot?](#what-is-parrrot)
2. [Supported Models](#supported-models)
3. [Installation](#installation)
4. [How It Works](#how-it-works)
5. [Project Structure](#project-structure)
6. [Core Modules](#core-modules)
7. [Tools Reference](#tools-reference)
8. [Configuration](#configuration)
9. [Memory System](#memory-system)
10. [Skills System](#skills-system)
11. [CLI Commands](#cli-commands)
12. [Common Errors](#common-errors)

---

## What is Parrrot?

Parrrot is a local-first personal AI assistant that:
- Controls your PC (mouse, keyboard, windows)
- Browses the web using a real browser (Chrome/Firefox via CDP or Playwright)
- Manages files and runs shell commands
- Remembers things persistently in JSON files at `~/.parrrot/`
- Runs autonomously in the background with a scheduler
- Supports extensible "skills" (plain Python files you drop into `~/.parrrot/skills/`)

---

## Supported Models

> **IMPORTANT: This build uses only the following two models, both accessed via Ollama Cloud:**
>
> | Tag (in config) | Ollama model name | How it runs |
> |---|---|---|
> | `qwen3.5:cloud` | `qwen3.5` | Ollama Cloud — NOT run locally |
> | `minimax-m2.7:cloud` | `minimax-m2.7` | Ollama Cloud — NOT run locally |
>
> **These are Ollama Cloud models.** Users do NOT run them natively on their machine.
> Ollama must be installed, but the `:cloud` tag tells Ollama to route the request to
> Ollama's cloud inference service instead of a locally downloaded model weight.
>
> You cannot use these models by just having Ollama installed locally — you need
> **Ollama Cloud access** (an Ollama account with cloud inference enabled).

### What "Ollama Cloud" means here

Ollama supports a `:cloud` tag suffix on model names. When a model is referenced as
`qwen3.5:cloud` or `minimax-m2.7:cloud`, Ollama does **not** download or run the model
weights locally. Instead it sends the request to Ollama's cloud inference backend.

This is different from:
- A **local** Ollama model (e.g. `qwen2.5`, `llama3.2`) — downloaded and run on your GPU/CPU
- A **native cloud API** (e.g. OpenAI, Anthropic) — called directly without Ollama

The flow for these models is:

```
User prompt
    │
    ▼
parrrot (router.py)
    │
    ▼
Ollama (local client, localhost:11434)
    │  sends request with model = "qwen3.5:cloud" or "minimax-m2.7:cloud"
    ▼
Ollama Cloud inference service   ← actual computation happens here, not on your machine
    │
    ▼
Response returned to parrrot
```

### How the `:cloud` tag is handled in code

In `parrrot/core/router.py`, the `_normalize_model()` function strips the `:cloud` suffix
for `kimi` and `minimax` providers when calling native cloud APIs directly. However, for
Ollama Cloud these models are passed through to the local Ollama client **with the `:cloud`
suffix kept intact**, because Ollama itself understands and requires that suffix to route
to cloud inference.

```python
# router.py — line 27-33
def _normalize_model(provider: str, model: str) -> str:
    if not model:
        return model
    if provider in ("kimi", "minimax") and ":" in model:
        return model.split(":", 1)[0]   # strips :cloud for native API calls only
    return model
```

### Setting the model in config

Edit `~/.parrrot/config.toml`:

```toml
[model]
mode = "local"                          # use "local" — Ollama handles cloud routing via the :cloud tag
local_model = "qwen3.5:cloud"          # or "minimax-m2.7:cloud"
local_url = "http://localhost:11434"   # Ollama must be running
```

> **Note:** Set `mode = "local"` even though these are cloud-inferred models. The `:cloud`
> tag in the model name is what tells Ollama to use cloud inference. Parrrot sends the
> request to your local Ollama instance, and Ollama forwards it to cloud.

Ollama Cloud requires you to be signed in to your Ollama account:

```bash
ollama login       # sign in to your Ollama account to enable cloud model access
ollama serve       # start the local Ollama server (must be running)
```

---

## Installation

### Quick install (recommended)

```bash
pip install parrrot
parrrot
```

### From source (for developers)

```bash
git clone https://github.com/Ahilan-1/parrrot
cd parrrot
python setup.py install        # or: pip install -e .
parrrot
```

### Fix "No module named 'parrrot'" error

If you see this error it means the package is not installed in your Python environment.
Run one of the following from the project root directory:

```bash
pip install -e .
# or
python setup.py install
```

See [Common Errors](#common-errors) for more details.

---

## How It Works

### High-level flow

```
User input
    │
    ▼
main.py (Typer CLI)
    │
    ├─ First run? → onboarding.py (setup wizard)
    │
    ▼
core/agent.py  ← main reasoning loop
    │
    ├── core/context.py   — builds the system prompt (injects memory + tool list)
    ├── core/router.py    — picks the LLM backend (local Ollama or cloud)
    │       ├── models/ollama_local.py   (HTTP → localhost:11434)
    │       └── models/ollama_cloud.py   (HTTP → MiniMax / OpenAI-compatible)
    │
    ├── Parse LLM response for tool calls
    ├── tools/registry.py — dispatches tool calls
    │       └── (any of 16 tool files)
    ├── Inject tool results back into conversation
    └── Loop until no more tool calls → return final answer
```

### Agent reasoning loop (`core/agent.py`)

The agent runs a **think → act → respond** loop:

1. Build system prompt via `core/context.py` (includes memory + all tool descriptions)
2. Send conversation to LLM via `core/router.py`
3. Parse the LLM response for tool call XML/JSON blocks
4. Execute each tool via `tools/registry.py`
5. Append tool results to the conversation
6. Repeat until no tool calls remain or max rounds reached
7. Return the final text answer

Key constants in `agent.py`:

| Constant | Value | Meaning |
|---|---|---|
| `MAX_TOOL_ROUNDS` | 25 | Max tool calls per continuation block |
| `MAX_AUTO_CONTINUES` | 5 | Max automatic continuation blocks |
| `TOOL_ERROR_ESCALATION_THRESHOLD` | 3 | Local errors before escalating to cloud |
| `MAX_TOOL_ROUNDS_ADVANCED` | 60 | For complex tasks |
| `MAX_AUTO_CONTINUES_ADVANCED` | 12 | For complex tasks |

**Complexity detection**: The agent inspects the user message for length and keywords
(`"and"`, `"then"`, `"workflow"`, etc.) to decide whether to use the normal or advanced
planning mode.

**Hybrid escalation**: In `hybrid` mode, if the local model fails more than
`TOOL_ERROR_ESCALATION_THRESHOLD` times, the agent escalates to the cloud model automatically.

### Tool call format

The LLM is instructed to emit tool calls in XML format:

```xml
<tool_call>
  <name>read_file</name>
  <parameters>{"path": "/home/user/notes.txt"}</parameters>
</tool_call>
```

`tools/registry.py` also handles JSON and Python-call-style formats as fallbacks.

---

## Project Structure

```
parrrot/
├── setup.py                  ← installation script (fixes "No module named 'parrrot'")
├── pyproject.toml            ← build config (hatchling)
├── README.md                 ← user-facing readme
├── DOCS.md                   ← this file
│
└── parrrot/                  ← Python package
    ├── __init__.py
    ├── main.py               CLI entry point — 10 commands via Typer
    ├── config.py             TOML config loader/saver
    ├── onboarding.py         First-run interactive setup wizard (Rich)
    │
    ├── core/
    │   ├── agent.py          Main think→act→respond loop
    │   ├── context.py        Builds system prompt with memory injection
    │   ├── memory.py         JSON-based persistent memory (facts/events/tasks)
    │   ├── router.py         Selects LLM backend (local / cloud / hybrid)
    │   ├── scheduler.py      APScheduler wrapper for background tasks
    │   └── learner.py        Self-learning engine (web search + skill generation)
    │
    ├── models/
    │   ├── base.py           Abstract BaseLLM interface
    │   ├── ollama_local.py   HTTP client for local Ollama (localhost:11434)
    │   └── ollama_cloud.py   OpenAI-compatible cloud API handler
    │
    ├── tools/                16 tool files registered via @registry.register
    │   ├── registry.py       Central dispatcher — parses XML/JSON tool calls
    │   ├── browser_cdp.py    Chrome DevTools Protocol automation (1017 lines)
    │   ├── browser_control.py Playwright automation
    │   ├── browser.py        High-level web search/navigation
    │   ├── chatgpt_tool.py   ChatGPT OCR interaction
    │   ├── uia_control.py    Windows UI Automation (accessibility tree)
    │   ├── pc_control.py     Mouse, keyboard, window control
    │   ├── screen.py         Screenshots + OCR (Tesseract)
    │   ├── email_tool.py     Gmail via Playwright
    │   ├── filesystem.py     File read/write/move/search/zip
    │   ├── shell.py          Shell command execution
    │   ├── system_info.py    CPU/memory/disk/processes
    │   ├── notifications.py  Windows toast notifications
    │   ├── calendar_tool.py  iCalendar (.ics) file parsing
    │   ├── youtube.py        Video info + transcript extraction
    │   └── learning_tools.py Self-learning integration
    │
    ├── skills/
    │   ├── loader.py         Scans ~/.parrrot/skills/ for .py skill files
    │   └── examples/         Example skills (clean_desktop, daily_briefing, …)
    │
    └── ui/
        ├── chat.py           Interactive chat (prompt_toolkit + Rich)
        └── dashboard.py      Daemon status display
```

---

## Core Modules

### `parrrot/core/agent.py` — Agent

The heart of Parrrot. `Agent.think_and_act(user_input)` runs the full reasoning loop.

```python
from parrrot.core.agent import Agent

agent = Agent()
result = await agent.think_and_act("What files are on my desktop?")
```

### `parrrot/core/router.py` — Router

Selects the right LLM backend based on `~/.parrrot/config.toml`.

- `mode = "local"` → Ollama at `http://localhost:11434`
- `mode = "cloud"` → cloud provider (MiniMax, OpenAI, etc.)
- `mode = "hybrid"` → local by default, escalates to cloud on repeated errors

```python
from parrrot.core.router import Router

router = Router()
response = await router.complete(request)
```

### `parrrot/core/memory.py` — Memory

Persistent, fuzzy-searchable JSON memory in `~/.parrrot/memory/`.

```python
from parrrot.core import memory

memory.remember("user_name", "Alice")
results = memory.recall("Alice")   # fuzzy search
memory.forget("user_name")
```

### `parrrot/models/ollama_cloud.py` — Cloud LLM

Sends requests to OpenAI-compatible cloud endpoints. MiniMax uses a non-standard
path (`/text/chatcompletion_v2` instead of `/chat/completions`) — this is handled
automatically.

### `parrrot/tools/registry.py` — Tool Registry

All tools are registered with a decorator:

```python
@registry.register("read_file", "Read a file from disk", {"path": "string"})
async def read_file(path: str) -> str:
    ...
```

---

## Tools Reference

| Tool name | File | What it does |
|---|---|---|
| `read_file`, `write_file`, `list_dir`, … | `filesystem.py` | File operations |
| `shell` | `shell.py` | Run terminal commands |
| `web_search`, `open_url` | `browser.py` | Web search and navigation |
| `cdp_navigate`, `cdp_click`, … | `browser_cdp.py` | Fast Chrome DevTools automation |
| `playwright_browse` | `browser_control.py` | Playwright browser fallback |
| `move_mouse`, `click`, `type_text` | `pc_control.py` | Mouse and keyboard control |
| `screenshot`, `ocr_screen` | `screen.py` | Screenshots and OCR |
| `uia_snapshot`, `uia_click` | `uia_control.py` | Windows accessibility tree |
| `send_email`, `read_emails` | `email_tool.py` | Gmail via browser |
| `get_video_info`, `get_transcript` | `youtube.py` | YouTube video info |
| `get_calendar_events` | `calendar_tool.py` | Read .ics calendar files |
| `notify` | `notifications.py` | Desktop notification |
| `get_system_info`, `list_processes` | `system_info.py` | System metrics |
| `learn_about`, `ask_chatgpt` | `learning_tools.py` | Self-learning |

---

## Configuration

Config file: `~/.parrrot/config.toml`

```toml
[identity]
name = "Parrrot"
user_name = "Alice"

[model]
mode = "local"                      # use "local" for Ollama Cloud models
local_model = "qwen3.5:cloud"       # or "minimax-m2.7:cloud" — Ollama routes :cloud to cloud inference
local_url = "http://localhost:11434"
cloud_provider = ""                 # leave empty when using Ollama Cloud via :cloud tag
cloud_model = ""
cloud_endpoint = ""
hybrid_threshold = "auto"           # "auto", "manual", or "never"

[permissions]
file_access = true
shell_access = true
mouse_keyboard = true
screen_capture = true
browser_control = true
notifications = true
autostart = false

[privacy]
local_first = true
log_conversations = false
telemetry = false

[scheduler]
heartbeat_interval = 300            # seconds between heartbeat checks
enabled = true

[ui]
theme = "dark"
show_tool_calls = true
compact_mode = false
```

### Supported cloud providers

| `cloud_provider` value | API endpoint | Env var for API key |
|---|---|---|
| `minimax` | `https://api.minimax.io/v1` | `MINIMAX_API_KEY` |
| `kimi` | `https://api.moonshot.ai/v1` | `KIMI_API_KEY` |
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `anthropic` | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| `google` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GOOGLE_API_KEY` |
| `custom` | Your own URL | stored in `secrets.json` |

---

## Memory System

All memory is stored as JSON in `~/.parrrot/memory/`:

| File | Contents |
|---|---|
| `facts.json` | Persistent key/value knowledge |
| `events.json` | Timestamped events |
| `tasks.json` | Active task tracking |
| `conversations.json` | Summarized past conversations |

Memory is injected into every system prompt (capped at 2000 chars). Fuzzy search
is powered by `rapidfuzz`; falls back to substring matching if unavailable.

The agent auto-compresses old messages into memory when the conversation hits 20+
messages.

---

## Skills System

Skills are plain Python files in `~/.parrrot/skills/`. Each skill defines:

```python
# ~/.parrrot/skills/daily_brief.py

SKILL_NAME = "Daily Briefing"
SKILL_DESCRIPTION = "Summarize emails and calendar at 8am"
SCHEDULE = "0 8 * * *"   # cron expression — omit for on-demand skills

async def run(agent, memory, tools):
    await agent.run_task("Summarize my unread emails and today's calendar.")
```

Install a skill:

```bash
parrrot skills add my_skill.py
parrrot daemon    # restart to activate
```

---

## CLI Commands

| Command | What it does |
|---|---|
| `parrrot` | First run → setup wizard; afterwards → opens chat |
| `parrrot chat` | Interactive chat session |
| `parrrot run "task"` | One-off task, print result, exit |
| `parrrot daemon` | Start background daemon (scheduler + global hotkey) |
| `parrrot stop` | Stop the background daemon |
| `parrrot status` | Show daemon status and active jobs |
| `parrrot memory` | Browse all stored memories |
| `parrrot memory "query"` | Fuzzy-search memories |
| `parrrot memory forget "key"` | Delete a memory entry |
| `parrrot config` | Open config file in your default editor |
| `parrrot skills` | List installed skills |
| `parrrot skills add file.py` | Install a skill |
| `parrrot hotkey` | Register Win+Shift+P global hotkey (standalone) |
| `parrrot update` | `pip install --upgrade parrrot` |

### In-chat slash commands

| Command | Action |
|---|---|
| `/new` or `/reset` | Clear conversation |
| `/status` | Show model, memory stats, config |
| `/model` | Show active model name |
| `/verbose` | Toggle verbose tool output |
| `/compact` | Compress conversation into memory |
| `/memory [query]` | Search or browse memories |
| `/tools` | List all registered tools |
| `/history` | Show command history |
| `/clear` | Clear the screen |
| `/help` | Show all commands |

---

## Common Errors

### `No module named 'parrrot'`

This happens when you run a script that imports `parrrot` without the package
being installed in the active Python environment.

**Fix:**

```bash
# From the project root directory:
pip install -e .

# Or using setup.py:
python setup.py install

# Or install from PyPI:
pip install parrrot
```

After installation, verify it works:

```bash
python -c "import parrrot; print('OK')"
parrrot --help
```

If you are using a virtual environment, make sure it is activated before installing.

---

### `ConnectionRefusedError` / `Can't reach the AI model`

Ollama is not running. Start it:

```bash
ollama serve
```

---

### `Model not found`

The model is not downloaded yet:

```bash
ollama pull llama3.2
```

---

### `Cloud LLM error (401)`

Your API key is missing or wrong. Set it:

```bash
export MINIMAX_API_KEY=your_key_here
```

Or run the setup wizard again: `parrrot` (if no config exists) or edit
`~/.parrrot/config.toml` and `~/.parrrot/secrets.json`.

---

### `cryptography package not found`

Secrets are saved as plain JSON (not encrypted). To enable encryption:

```bash
pip install cryptography
```
