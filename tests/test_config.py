"""Tests for config module."""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def temp_config(tmp_path, monkeypatch):
    """Redirect config to temp dir."""
    monkeypatch.setattr("parrrot.config.PARRROT_DIR", tmp_path)
    monkeypatch.setattr("parrrot.config.CONFIG_PATH", tmp_path / "config.toml")
    yield tmp_path


def test_is_first_run_when_no_config():
    from parrrot.config import is_first_run
    assert is_first_run() is True


def test_load_returns_defaults():
    from parrrot.config import load
    conf = load()
    assert conf["identity"]["name"] == "Parrrot"
    assert conf["model"]["mode"] == "local"


def test_save_and_load_roundtrip(tmp_path):
    from parrrot.config import save, load

    conf = load()
    conf["identity"]["name"] = "Jarvis"
    conf["model"]["local_model"] = "mistral"
    save(conf)

    loaded = load()
    assert loaded["identity"]["name"] == "Jarvis"
    assert loaded["model"]["local_model"] == "mistral"


def test_get_nested_key():
    from parrrot.config import get, save, load

    conf = load()
    conf["identity"]["name"] = "Friday"
    save(conf)

    assert get("identity.name") == "Friday"


def test_set_value():
    from parrrot.config import set_value, get

    set_value("identity.name", "Nova")
    assert get("identity.name") == "Nova"


def test_is_first_run_false_after_save():
    from parrrot.config import save, load, is_first_run
    save(load())
    assert is_first_run() is False
