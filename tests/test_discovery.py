import os
import shutil
from datetime import date
from pathlib import Path

import pytest

from tokenscope.discovery import (
    CLAUDE,
    CODEX,
    UnknownFormatError,
    detect_format,
    discover_sessions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_detects_both_formats():
    assert detect_format(FIXTURES / "claude" / "basic.jsonl") == CLAUDE
    assert detect_format(FIXTURES / "codex" / "basic.jsonl") == CODEX


def test_unknown_format_errors(tmp_path):
    bad = tmp_path / "x.jsonl"
    bad.write_text('{"hello": "world"}\nnot json\n')
    with pytest.raises(UnknownFormatError):
        detect_format(bad)
    empty = tmp_path / "e.jsonl"
    empty.write_text("")
    with pytest.raises(UnknownFormatError):
        detect_format(empty)


def test_recurses_directories(tmp_path):
    a = tmp_path / "a" / "b" / "one.jsonl"
    a.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "claude" / "basic.jsonl", a)
    b = tmp_path / "two.jsonl"
    shutil.copy(FIXTURES / "codex" / "basic.jsonl", b)
    (tmp_path / "ignore.txt").write_text("x")
    assert discover_sessions(tmp_path) == sorted([a, b])
    assert discover_sessions(b) == [b]


def test_since_filter(tmp_path):
    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    old.write_text("{}\n")
    new.write_text("{}\n")
    os.utime(old, (1_600_000_000, 1_600_000_000))
    assert discover_sessions(tmp_path, since=date(2024, 1, 1)) == [new]
    assert discover_sessions(tmp_path) == sorted([old, new])


def test_default_locations(tmp_path, monkeypatch):
    # POSIX expands "~" from HOME; Windows expands it from USERPROFILE, so set both.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    f = tmp_path / ".claude" / "projects" / "p" / "s.jsonl"
    g = tmp_path / ".codex" / "sessions" / "2025" / "r.jsonl"
    for p in (f, g):
        p.parent.mkdir(parents=True)
        p.write_text("{}\n")
    assert discover_sessions() == sorted([f, g])
