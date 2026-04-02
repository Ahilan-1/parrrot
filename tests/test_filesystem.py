"""Tests for filesystem tools."""

import os
import tempfile
from pathlib import Path

import pytest


def test_write_and_read_file(tmp_path):
    from parrrot.tools.filesystem import _write_file, _read_file

    p = str(tmp_path / "test.txt")
    result = _write_file(p, "Hello, Parrrot!")
    assert "Written" in result

    content = _read_file(p)
    assert content == "Hello, Parrrot!"


def test_list_files(tmp_path):
    from parrrot.tools.filesystem import _list_files

    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    result = _list_files(str(tmp_path))
    assert "a.txt" in result
    assert "b.txt" in result


def test_move_file(tmp_path):
    from parrrot.tools.filesystem import _move_file

    src = tmp_path / "source.txt"
    src.write_text("move me")
    dst = str(tmp_path / "dest.txt")

    result = _move_file(str(src), dst)
    assert "Moved" in result
    assert Path(dst).exists()
    assert not src.exists()


def test_delete_file(tmp_path):
    from parrrot.tools.filesystem import _delete_file

    p = tmp_path / "todelete.txt"
    p.write_text("bye")

    result = _delete_file(str(p))
    assert "Deleted" in result
    assert not p.exists()


def test_search_files(tmp_path):
    from parrrot.tools.filesystem import _search_files

    (tmp_path / "invoice_2024.pdf").write_text("fake pdf")
    (tmp_path / "notes.txt").write_text("notes")

    result = _search_files("invoice", str(tmp_path))
    assert "invoice_2024.pdf" in result


def test_read_nonexistent_file():
    from parrrot.tools.filesystem import _read_file

    result = _read_file("/nonexistent/path/file.txt")
    assert "not found" in result.lower()
