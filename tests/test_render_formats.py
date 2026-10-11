import json
from datetime import datetime
from pathlib import Path

from tokenscope.models import Session, ToolCall, ToolResult, Turn, Usage
from tokenscope.render_json import render_json
from tokenscope.render_markdown import render_markdown
from tokenscope.report import build_report

GOLDEN_MARKDOWN = Path(__file__).parent / "golden" / "report.md"

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


def test_render_json_parses() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_json(report)
    data = json.loads(rendered)
    assert isinstance(data, dict)


def test_render_json_contains_schema_version() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_json(report)
    data = json.loads(rendered)
    assert "schema_version" in data
    assert isinstance(data["schema_version"], str)


def test_render_json_contains_all_sections() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_json(report)
    data = json.loads(rendered)
    required_keys = [
        "schema_version",
        "sessions",
        "usage",
        "cost",
        "cache_hit_ratio",
        "tool_spend",
        "rereads",
        "oversized",
        "cache_misses",
        "suggestions",
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"


def test_render_markdown_matches_golden_file() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_markdown(report, top_n=10)
    assert rendered == GOLDEN_MARKDOWN.read_text()


def test_render_markdown_respects_top_n() -> None:
    report = build_report(_fixture_sessions())
    rendered = render_markdown(report, top_n=0)
    assert "src/a.py" not in rendered
    assert "npm test" not in rendered
