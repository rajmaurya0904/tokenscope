import pytest

from tokenscope.analyzers.tool_spend import analyze_tool_spend
from tokenscope.models import Session, ToolCall, ToolResult, Turn


def _session() -> Session:
    m = "claude-sonnet-4"  # input 3.0, cache_read 0.3 per million
    return Session(
        id="s",
        provider="claude",
        turns=[
            Turn(
                index=0,
                model=m,
                tool_calls=[ToolCall("a", "Read"), ToolCall("b", "Bash")],
                tool_results=[
                    ToolResult("a", "x" * 4000),  # 1000 tokens
                    ToolResult("b", "y" * 400),  # 100 tokens
                ],
            ),
            Turn(
                index=1,
                model=m,
                tool_calls=[ToolCall("c", "Bash")],
                tool_results=[ToolResult("c", "z" * 400)],  # 100 tokens
            ),
            Turn(index=2, model=m),
        ],
    )


def test_tool_totals_and_sorting() -> None:
    result = analyze_tool_spend(_session())
    assert [r.tool for r in result] == ["Read", "Bash"]
    read, bash = result
    # Read: 1000 tok, carried over 2 later turns
    assert (read.calls, read.output_tokens, read.carried_tokens) == (1, 1000, 2000)
    assert read.cost == pytest.approx(1000 * 3 / 1e6 + 2000 * 0.3 / 1e6)
    # Bash: 100 (carried x2) + 100 (carried x1)
    assert (bash.calls, bash.output_tokens, bash.carried_tokens) == (2, 200, 300)
    assert bash.cost == pytest.approx(200 * 3 / 1e6 + 300 * 0.3 / 1e6)


def test_pluggable_tokenizer() -> None:
    result = analyze_tool_spend(_session(), tokenizer=lambda s: 1)
    assert {r.tool: r.output_tokens for r in result} == {"Read": 1, "Bash": 2}
