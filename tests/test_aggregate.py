"""Tests for cross-session aggregation: totals, session ranking, and project/day buckets."""

from __future__ import annotations

from datetime import datetime

import pytest

from tokenscope.aggregate import aggregate_sessions, session_day, session_project
from tokenscope.models import Session, ToolCall, ToolResult, Turn, Usage

_MODEL = "claude-sonnet-4"  # input 3.0, output 15.0 per million: higher usage -> higher cost


def _session(
    id: str,
    path: str,
    day: datetime,
    input_tokens: int,
    output_tokens: int,
    reread_path: str | None = None,
    oversized_command: str | None = None,
) -> Session:
    turns = [
        Turn(
            index=0,
            timestamp=day,
            model=_MODEL,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        )
    ]
    if reread_path:
        turns.append(
            Turn(
                index=1,
                timestamp=day,
                model=_MODEL,
                tool_calls=[ToolCall("r1", "Read", {"file_path": reread_path})],
                tool_results=[ToolResult("r1", "x" * 40)],
            )
        )
        turns.append(
            Turn(
                index=2,
                timestamp=day,
                model=_MODEL,
                tool_calls=[ToolCall("r2", "Read", {"file_path": reread_path})],
                tool_results=[ToolResult("r2", "y" * 40)],  # re-read with no edit: wasted
            )
        )
    if oversized_command:
        turns.append(
            Turn(
                index=3,
                timestamp=day,
                model=_MODEL,
                tool_calls=[ToolCall("o1", "Bash", {"command": oversized_command})],
                tool_results=[ToolResult("o1", "z" * 20001)],  # 5001 tokens: over the threshold
            )
        )
    return Session(id=id, provider="claude", turns=turns, path=path)


def _fixture_sessions() -> list[Session]:
    session_a = _session(
        "s1",
        "/home/u/.claude/projects/proj-alpha/s1.jsonl",
        datetime(2024, 1, 1, 0, 0, 0),
        input_tokens=500,
        output_tokens=200,
        reread_path="src/a.py",
    )
    session_b = _session(
        "s2",
        "/home/u/.claude/projects/proj-alpha/s2.jsonl",
        datetime(2024, 1, 2, 0, 0, 0),
        input_tokens=100,
        output_tokens=50,
        oversized_command="npm test",
    )
    session_c = _session(
        "s3",
        "/home/u/.claude/projects/proj-beta/s3.jsonl",
        datetime(2024, 1, 1, 0, 0, 0),
        input_tokens=300,
        output_tokens=100,
    )
    return [session_a, session_b, session_c]


def test_session_project_from_parent_dir() -> None:
    session = _fixture_sessions()[0]
    assert session_project(session) == "proj-alpha"


def test_session_project_unknown_when_no_path() -> None:
    session = Session(id="s", provider="claude", turns=[])
    assert session_project(session) == "unknown"


def test_session_day_from_earliest_turn() -> None:
    session = _fixture_sessions()[0]
    assert session_day(session) == "2024-01-01"


def test_session_day_none_when_untimed() -> None:
    session = Session(id="s", provider="claude", turns=[Turn(index=0)])
    assert session_day(session) is None


def test_aggregate_sums_totals_across_two_sessions() -> None:
    sessions = _fixture_sessions()[:2]
    agg = aggregate_sessions(sessions, group_by="project")

    assert agg.session_count == 2
    assert agg.usage.input_tokens == 600
    assert agg.usage.output_tokens == 250
    assert agg.cost == pytest.approx(sum(t.cost for t in agg.sessions))
    assert agg.cost > 0


def test_aggregate_ranks_sessions_by_cost_descending() -> None:
    agg = aggregate_sessions(_fixture_sessions(), group_by="project")
    costs = [t.cost for t in agg.sessions]

    assert costs == sorted(costs, reverse=True)
    assert agg.sessions[0].id == "s1"  # highest token usage -> highest cost


def test_group_by_project_merges_same_project_sessions() -> None:
    agg = aggregate_sessions(_fixture_sessions(), group_by="project")
    keys = {g.key for g in agg.groups}
    assert keys == {"proj-alpha", "proj-beta"}

    alpha = next(g for g in agg.groups if g.key == "proj-alpha")
    assert alpha.session_count == 2
    assert alpha.usage.input_tokens == 600  # 500 (s1) + 100 (s2)

    beta = next(g for g in agg.groups if g.key == "proj-beta")
    assert beta.session_count == 1
    assert beta.usage.input_tokens == 300


def test_group_by_project_merges_rereads_and_oversized() -> None:
    agg = aggregate_sessions(_fixture_sessions(), group_by="project")
    alpha = next(g for g in agg.groups if g.key == "proj-alpha")

    assert len(alpha.rereads) == 1
    assert alpha.rereads[0].path == "src/a.py"
    assert alpha.rereads[0].wasted_reads == 1

    assert len(alpha.oversized) == 1
    assert alpha.oversized[0].command == "npm test"


def test_group_by_day_produces_separate_buckets() -> None:
    agg = aggregate_sessions(_fixture_sessions(), group_by="day")
    keys = {g.key for g in agg.groups}
    assert keys == {"2024-01-01", "2024-01-02"}

    day1 = next(g for g in agg.groups if g.key == "2024-01-01")
    assert day1.session_count == 2  # s1 (proj-alpha) + s3 (proj-beta), same day
    assert day1.usage.input_tokens == 800  # 500 + 300

    day2 = next(g for g in agg.groups if g.key == "2024-01-02")
    assert day2.session_count == 1
    assert day2.usage.input_tokens == 100


def test_invalid_group_by_raises() -> None:
    with pytest.raises(ValueError):
        aggregate_sessions(_fixture_sessions(), group_by="bogus")
