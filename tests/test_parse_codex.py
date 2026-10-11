from pathlib import Path

from tokenscope.models import Usage
from tokenscope.parse_codex import parse_codex_session

FIXTURE = Path(__file__).parent / "fixtures" / "codex" / "basic.jsonl"


def test_turns_and_metadata():
    s = parse_codex_session(FIXTURE)
    assert s.provider == "codex"
    assert s.id == "codex-sess-1"
    assert len(s.turns) == 3
    assert s.turns[0].model == "gpt-5-codex"
    assert s.turns[0].timestamp.year == 2025


def test_tool_names_and_pairing():
    t0, t1, t2 = parse_codex_session(FIXTURE).turns
    assert [(c.id, c.name) for c in t0.tool_calls] == [("call_1", "Bash")]
    assert t0.tool_calls[0].input["command"][-1] == "cat a.py"
    assert [(r.tool_call_id, r.content, r.is_error) for r in t0.tool_results] == [
        ("call_1", "print(1)\n", False)
    ]
    assert [(c.id, c.name) for c in t1.tool_calls] == [("call_2", "Edit"), ("call_3", "Read")]
    assert [(r.tool_call_id, r.content, r.is_error) for r in t1.tool_results] == [
        ("call_2", "patched", False),
        ("call_3", "nope", True),
    ]
    assert not t2.tool_calls


def test_token_deltas_sum_to_final_total():
    s = parse_codex_session(FIXTURE)
    assert [t.usage.total_tokens for t in s.turns] == [130, 200, 160]
    assert s.turns[0].usage == Usage(input_tokens=80, output_tokens=30, cache_read_tokens=20)
    assert s.usage.total_tokens == 490
    assert s.usage == Usage(input_tokens=150, output_tokens=90, cache_read_tokens=250)
