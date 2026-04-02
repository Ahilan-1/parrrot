"""Tests for the memory module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def temp_memory_dir(tmp_path, monkeypatch):
    """Redirect memory to a temp dir for each test."""
    monkeypatch.setattr("parrrot.core.memory.MEMORY_DIR", tmp_path)
    yield tmp_path


def test_remember_and_recall():
    from parrrot.core.memory import remember, recall

    remember("test_key", "hello world")
    results = recall("hello")
    assert any(r["key"] == "test_key" for r in results)


def test_remember_and_get():
    from parrrot.core.memory import remember, get

    remember("user_name", "Alice")
    assert get("user_name") == "Alice"


def test_forget():
    from parrrot.core.memory import remember, get, forget

    remember("to_delete", "value")
    assert get("to_delete") == "value"
    assert forget("to_delete") is True
    assert get("to_delete") is None


def test_build_context():
    from parrrot.core.memory import remember, build_context

    remember("favorite_color", "blue")
    context = build_context()
    assert "favorite_color" in context
    assert "blue" in context


def test_count():
    from parrrot.core.memory import remember, count

    remember("k1", "v1", category="facts")
    remember("k2", "v2", category="events")
    counts = count()
    assert counts["facts"] >= 1
    assert counts["events"] >= 1


def test_recall_returns_empty_for_no_match():
    from parrrot.core.memory import recall

    results = recall("zzznomatch_xyz_abc_123")
    assert results == []
