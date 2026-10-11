"""Tests for the examples/ directory: ``tokenscope analyze examples/`` and its reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenscope.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_analyze_examples_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(EXAMPLES)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Cost & Waste Report" in out
    assert "Sessions: 2" in out


@pytest.mark.parametrize("name", ["report.txt", "report.json", "report.md"])
def test_report_files_exist(name: str) -> None:
    path = EXAMPLES / "reports" / name
    assert path.is_file()
    assert path.stat().st_size > 0
