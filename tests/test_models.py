from tokenscope.models import Session, ToolCall, ToolResult, Turn, Usage


def test_usage_total_and_add() -> None:
    a = Usage(input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_creation_tokens=4)
    assert a.total_tokens == 10
    assert (a + Usage(input_tokens=5)).total_tokens == 15
    assert Usage().total_tokens == 0


def test_construct_session_graph() -> None:
    call = ToolCall(id="t1", name="Read", input={"file_path": "a.py"})
    result = ToolResult(tool_call_id="t1", content="x", is_error=False)
    turn = Turn(index=0, usage=Usage(input_tokens=7, output_tokens=3), tool_calls=[call],
                tool_results=[result])
    session = Session(id="s", provider="claude", turns=[turn, Turn(index=1, usage=Usage(2))])
    assert session.turns[0].tool_calls[0].name == "Read"
    assert session.turns[0].tool_results[0].tool_call_id == "t1"
    assert session.usage == Usage(input_tokens=9, output_tokens=3)
