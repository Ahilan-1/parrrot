"""
Parrrot — Config loader/saver (TOML)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

PARRROT_DIR = Path.home() / ".parrrot"
CONFIG_PATH = PARRROT_DIR / "config.toml"

_DEFAULTS: dict[str, Any] = {
    "identity": {"name": "Parrrot", "user_name": ""},
    "model": {
        "mode": "local",
        "local_model": "llama3.2",
        "local_url": "http://localhost:11434",
        "cloud_provider": "",
        "cloud_model": "",
        "cloud_endpoint": "",
        "hybrid_threshold": "auto",
    },
    "permissions": {
        "file_access": True,
        "shell_access": True,
        "mouse_keyboard": True,
        "screen_capture": True,
        "browser_control": True,
        "notifications": True,
        "autostart": False,
    },
    "privacy": {
        "local_first": True,
        "log_conversations": False,
        "telemetry": False,
    },
    "scheduler": {
        "heartbeat_interval": 300,
        "enabled": True,
    },
    "ui": {
        "theme": "dark",
        "show_tool_calls": True,
        "compact_mode": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict[str, Any]:
    """Load config from disk, merging with defaults."""
    if not CONFIG_PATH.exists():
        return dict(_DEFAULTS)
    with open(CONFIG_PATH, "rb") as f:
        on_disk = tomllib.load(f)
    return _deep_merge(_DEFAULTS, on_disk)


def save(config: dict[str, Any]) -> None:
    """Save config to disk, stripping internal keys (prefixed with _)."""
    PARRROT_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in config.items() if not k.startswith("_")}
    CONFIG_PATH.write_bytes(tomli_w.dumps(clean).encode())


def is_first_run() -> bool:
    """True if no config file exists yet."""
    return not CONFIG_PATH.exists()


def get(key: str, default: Any = None) -> Any:
    """Quick accessor: get("model.local_model")."""
    cfg = load()
    parts = key.split(".")
    node: Any = cfg
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return default
        if node is None:
            return default
    return node


def set_value(key: str, value: Any) -> None:
    """Quick setter: set_value("model.local_model", "mistral")."""
    cfg = load()
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    save(cfg)
