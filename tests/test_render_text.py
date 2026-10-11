from datetime import datetime
from pathlib import Path

from tokenscope.models import Session, ToolCall, ToolResult, Turn, Usage
from tokenscope.render_text import render_text
from tokenscope.report import build_report

GOLDEN = Path(__file__).parent / "golden" / "report.txt"

_MODEL = "claude-sonnet-4"  # input 3.0, output 15.0, cache_read 0.3, cache_write 3.0 per million


def _fixture_sessions() -> list[Session]:
    session_a = Session(
        id="s1",
        provider="claude",
        turns=[
            Turn(
                index=0,
                timestamp=datetime(2024, 1, 1, 0, 0, 0),
                model=_MODEL,
                usage=Usage(input_tokens=500, output_tokens=200),
                tool_calls=[ToolCall("a", "Read", {"file_path": "src/a.py"})],
                tool_results=[ToolResult("a", "x" * 20001)],  # 5001 tokens: oversized, no limit
            ),
            Turn(
                index=1,
                timestamp=datetime(2024, 1, 1, 0, 1, 0),
                model=_MODEL,
                usage=Usage(input_tokens=300, output_tokens=150),
                tool_calls=[ToolCall("b", "Read", {"file_path": "src/a.py"})],
                tool_results=[ToolResult("b", "y" * 400)],  # re-read with no edit in between
            ),
            Turn(
                index=2,
                timestamp=datetime(2024, 1, 1, 0, 20, 0),  # 19 min gap: cache miss
                model=_MODEL,
                usage=Usage(input_tokens=100, output_tokens=50, cache_creation_tokens=6000),
                tool_calls=[ToolCall("c", "Bash", {"command": "npm test"})],
                tool_results=[ToolResult("c", "z" * 400)],
            ),
        ],
    )
    session_b = Session(
        id="s2",
        provider="claude",
        turns=[
            Turn(
                index=0,
                timestamp=datetime(2024, 1, 2, 0, 0, 0),
                model=_MODEL,
                usage=Usage(input_tokens=50, output_tokens=20),
                tool_calls=[ToolCall("d", "Bash", {"command": "npm test"})],
                tool_results=[ToolResult("d", "w" * 400)],
            ),
        ],
    )
    return [session_a, session_b]


def test_render_text_matches_golden_file() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_text(report, top_n=10, color=False)
    assert rendered == GOLDEN.read_text()


def test_render_text_respects_top_n() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_text(report, top_n=0, color=False)
    assert "src/a.py" not in rendered
    assert "npm test" not in rendered


def test_render_text_empty_oversized_states_threshold() -> None:
    report = build_report(_fixture_sessions(), oversized_threshold=900_000)
    rendered = render_text(report, color=False)
    assert "(none above 900,000 tokens -- raise with --threshold)" in rendered
    assert "  (none)" not in rendered


def test_render_text_empty_rereads_explains_why() -> None:
    report = build_report([])
    rendered = render_text(report, color=False)
    assert "none -- no file was read twice without an edit in between" in rendered
    assert "(none above 5,000 tokens -- raise with --threshold)" in rendered


def test_render_text_color_only_when_requested() -> None:
    report = build_report(_fixture_sessions())
    assert "\x1b[" not in render_text(report, color=False)
    assert "\x1b[" in render_text(report, color=True)
