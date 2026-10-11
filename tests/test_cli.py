"""Tests for the ``tokenscope`` CLI: analyze and sessions subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenscope.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_FIXTURE = str(FIXTURES / "claude" / "basic.jsonl")
CODEX_FIXTURE = str(FIXTURES / "codex" / "basic.jsonl")


def test_analyze_exits_zero_with_expected_sections(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, CODEX_FIXTURE])
    out = capsys.readouterr().out

    assert code == 0
    assert "Cost & Waste Report" in out
    assert "Per-tool spend" in out
    assert "Repeated re-reads" in out
    assert "Oversized outputs" in out
    assert "Cache misses" in out
    assert "Suggestions" in out


def test_analyze_format_json_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, CODEX_FIXTURE, "--format", "json"])
    out = capsys.readouterr().out

    assert code == 0
    data = json.loads(out)
    assert data["schema_version"]
    assert data["sessions"] == 2


def test_analyze_format_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, "--format", "markdown"])
    out = capsys.readouterr().out

    assert code == 0
    assert out.startswith("# Cost & Waste Report")


def test_analyze_since_filters_out_everything(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, "--format", "json", "--since", "2099-01-01"])
    out = capsys.readouterr().out

    assert code == 0
    assert json.loads(out)["sessions"] == 0


def test_analyze_min_savings_filters_suggestions(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, "--format", "json", "--min-savings", "1000000"])
    out = capsys.readouterr().out

    assert code == 0
    assert json.loads(out)["suggestions"] == []


def test_analyze_group_by_project_text(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, CODEX_FIXTURE, "--group-by", "project"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Grouped by project" in out
    assert "Sessions ranked by cost" in out


def test_analyze_group_by_day_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", CLAUDE_FIXTURE, CODEX_FIXTURE, "--format", "json", "--group-by", "day"])
    out = capsys.readouterr().out

    assert code == 0
    data = json.loads(out)
    assert data["aggregate"]["group_by"] == "day"
    assert len(data["aggregate"]["sessions"]) == 2


def test_sessions_lists_fixtures(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["sessions", CLAUDE_FIXTURE, CODEX_FIXTURE])
    out = capsys.readouterr().out

    assert code == 0
    assert "sess-1" in out
    assert "codex-sess-1" in out
    assert "claude" in out
    assert "codex" in out


def test_sessions_format_json_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["sessions", CLAUDE_FIXTURE, CODEX_FIXTURE, "--format", "json"])
    out = capsys.readouterr().out

    assert code == 0
    rows = json.loads(out)
    assert {r["id"] for r in rows} == {"sess-1", "codex-sess-1"}
    assert all(r["size_bytes"] > 0 for r in rows)


def test_no_command_prints_help_and_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    out = capsys.readouterr().out

    assert code == 1
    assert "usage" in out
