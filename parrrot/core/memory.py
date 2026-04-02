"""
Parrrot — Local JSON memory system
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz, process as rfprocess
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

MEMORY_DIR = Path.home() / ".parrrot" / "memory"

_STORES = ("facts", "events", "tasks", "conversations")


# ---------------------------------------------------------------------------
# Low-level JSON store helpers
# ---------------------------------------------------------------------------

def _store_path(store: str) -> Path:
    return MEMORY_DIR / f"{store}.json"


def _load_store(store: str) -> dict[str, Any]:
    path = _store_path(store)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_store(store: str, data: dict[str, Any]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _store_path(store).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def remember(key: str, value: Any, category: str = "facts") -> None:
    """
    Save a fact, event, task, or conversation entry.

    Example:
        remember("user_name", "Alex")
        remember("last_email_check", "2024-01-01T08:00:00", category="events")
    """
    if category not in _STORES:
        category = "facts"
    store = _load_store(category)
    store[key] = {
        "value": value,
        "timestamp": time.time(),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_store(category, store)


def recall(query: str, category: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """
    Fuzzy-search memory for a query string.
    Returns a list of matching entries with their keys and scores.
    """
    stores_to_search = [category] if category and category in _STORES else list(_STORES)
    results: list[dict[str, Any]] = []

    for store_name in stores_to_search:
        store = _load_store(store_name)
        for key, entry in store.items():
            value_str = str(entry.get("value", ""))
            combined = f"{key} {value_str}"
            if _HAS_RAPIDFUZZ:
                score = fuzz.partial_ratio(query.lower(), combined.lower())
            else:
                # Simple substring match fallback
                score = 80 if query.lower() in combined.lower() else 0
            if score >= 50:
                results.append({
                    "key": key,
                    "value": entry.get("value"),
                    "category": store_name,
                    "updated": entry.get("updated", ""),
                    "score": score,
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def forget(key: str, category: str | None = None) -> bool:
    """
    Remove a memory entry by key.
    If category is None, searches all stores.
    Returns True if something was deleted.
    """
    stores_to_search = [category] if category else list(_STORES)
    deleted = False
    for store_name in stores_to_search:
        store = _load_store(store_name)
        if key in store:
            del store[key]
            _save_store(store_name, store)
            deleted = True
    return deleted


def get(key: str, category: str = "facts", default: Any = None) -> Any:
    """Retrieve a specific memory entry by exact key."""
    store = _load_store(category)
    entry = store.get(key)
    if entry is None:
        return default
    return entry.get("value", default)


def all_facts() -> dict[str, Any]:
    """Return all facts as {key: value} dict."""
    store = _load_store("facts")
    return {k: v["value"] for k, v in store.items()}


def build_context(max_chars: int = 3000) -> str:
    """
    Build a memory summary string to inject into the LLM system prompt.
    Includes recent facts, events, and active tasks.
    """
    parts: list[str] = []

    facts = _load_store("facts")
    if facts:
        lines = ["## Known facts"]
        for key, entry in list(facts.items())[:30]:
            lines.append(f"- {key}: {entry['value']}")
        parts.append("\n".join(lines))

    events = _load_store("events")
    if events:
        # Sort by timestamp, show most recent
        sorted_events = sorted(events.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)
        lines = ["## Recent events"]
        for key, entry in sorted_events[:10]:
            lines.append(f"- [{entry.get('updated', '')}] {key}: {entry['value']}")
        parts.append("\n".join(lines))

    tasks = _load_store("tasks")
    active_tasks = {k: v for k, v in tasks.items() if v.get("value", {}).get("status") == "active"}
    if active_tasks:
        lines = ["## Active tasks"]
        for key, entry in active_tasks.items():
            task = entry["value"]
            lines.append(f"- {key}: {task.get('description', '')}")
        parts.append("\n".join(lines))

    context = "\n\n".join(parts)
    return context[:max_chars] if len(context) > max_chars else context


def save_conversation_summary(messages: list[dict], summary: str) -> None:
    """Save a compressed summary of a conversation to memory."""
    key = f"conv_{int(time.time())}"
    remember(key, {"summary": summary, "message_count": len(messages)}, category="conversations")


def count() -> dict[str, int]:
    """Return count of entries per store."""
    return {store: len(_load_store(store)) for store in _STORES}
