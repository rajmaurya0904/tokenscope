from pathlib import Path

from tokenscope.models import Usage
from tokenscope.parse_claude import parse_claude_session

FIXTURE = Path(__file__).parent / "fixtures" / "claude" / "basic.jsonl"


def test_turns_and_metadata():
    s = parse_claude_session(FIXTURE)
    assert s.provider == "claude"
    assert s.id == "sess-1"
    assert len(s.turns) == 3
    assert s.turns[0].model == "claude-sonnet-4"
    assert s.turns[0].timestamp.year == 2025
    assert [t.is_sidechain for t in s.turns] == [False, False, True]


def test_tool_calls_paired_with_results():
    s = parse_claude_session(FIXTURE)
    t0, t1, _ = s.turns
    assert [c.id for c in t0.tool_calls] == ["toolu_1"]
    assert t0.tool_calls[0].input == {"command": "ls"}
    assert [(r.tool_call_id, r.content, r.is_error) for r in t0.tool_results] == [
        ("toolu_1", "a.py\nb.py", False)
    ]
    assert t1.tool_results[0].is_error and t1.tool_results[0].content == "boom"


def test_duplicate_message_ids_counted_once():
    s = parse_claude_session(FIXTURE)
    assert s.turns[0].usage == Usage(10, 20, 100, 5)
    assert s.usage == Usage(45, 42, 210, 5)
