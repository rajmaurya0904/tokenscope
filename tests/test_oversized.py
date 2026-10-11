from tcwa.analyzers.oversized import analyze_oversized
from tcwa.models import Session, ToolCall, ToolResult, Turn


def _turn(i: int, name: str, inp: dict, out: str = "") -> Turn:
    cid = f"c{i}"
    return Turn(index=i, tool_calls=[ToolCall(cid, name, inp)], tool_results=[ToolResult(cid, out)])


def _session(*turns: Turn) -> Session:
    return Session(id="s", provider="claude", turns=list(turns))


def test_results_above_threshold_flagged() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "npm test"}, "x" * 20001),  # 5001 tokens
    )
    [r] = analyze_oversized(s, threshold=5000)
    assert r.tool == "Bash"
    assert r.command == "npm test"
    assert r.estimated_tokens == 5001  # 20001 / 4 rounded up


def test_results_below_threshold_not_flagged() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "npm test"}, "x" * 4000),  # 1000 tokens
    )
    assert analyze_oversized(s, threshold=5000) == []


def test_threshold_exact_boundary_not_flagged() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "npm test"}, "x" * 20000),  # 5000 tokens exactly
    )
    assert analyze_oversized(s, threshold=5000) == []


def test_results_ordered_by_size_descending() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "cmd1"}, "x" * 20001),  # 5001 tokens
        _turn(1, "Read", {"file_path": "a.log"}, "y" * 35001),  # 8751 tokens
        _turn(2, "Bash", {"command": "cmd2"}, "z" * 25001),  # 6251 tokens
    )
    results = analyze_oversized(s, threshold=5000)
    assert len(results) == 3
    assert results[0].estimated_tokens > results[1].estimated_tokens > results[2].estimated_tokens
    assert results[0].command == "a.log"
    assert results[1].command == "cmd2"
    assert results[2].command == "cmd1"


def test_threshold_is_configurable() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "cmd"}, "x" * 20001),  # 5001 tokens
    )
    # With default threshold (5000), should be flagged
    assert len(analyze_oversized(s)) == 1
    # With high threshold, should not be flagged
    assert len(analyze_oversized(s, threshold=10000)) == 0
    # With low threshold, should be flagged
    assert len(analyze_oversized(s, threshold=1000)) == 1


def test_extracts_read_file_path() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "/path/to/big.log"}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.tool == "Read"
    assert r.command == "/path/to/big.log"


def test_extracts_bash_command() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "cat huge_file.txt"}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.tool == "Bash"
    assert r.command == "cat huge_file.txt"


def test_handles_bash_command_as_list() -> None:
    s = _session(
        _turn(0, "Bash", {"command": ["bash", "-c", "find . -type f"]}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.tool == "Bash"
    assert r.command == "bash -c find . -type f"


def test_read_with_no_limit_detected() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "big.log"}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.has_no_limit is True


def test_read_with_limit_not_marked_no_limit() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "big.log", "limit": 1000}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.has_no_limit is False


def test_read_with_offset_not_marked_no_limit() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "big.log", "offset": 100}, "x" * 20001),
    )
    [r] = analyze_oversized(s)
    assert r.has_no_limit is False


def test_multiple_results_in_same_turn() -> None:
    big_out = "x" * 20001
    cid1, cid2 = "c1", "c2"
    s = Session(
        id="s",
        provider="claude",
        turns=[
            Turn(
                index=0,
                tool_calls=[
                    ToolCall(cid1, "Read", {"file_path": "a.log"}),
                    ToolCall(cid2, "Bash", {"command": "ls"}),
                ],
                tool_results=[
                    ToolResult(cid1, big_out),
                    ToolResult(cid2, big_out),
                ],
            )
        ],
    )
    results = analyze_oversized(s)
    assert len(results) == 2
    tools = {r.tool for r in results}
    assert tools == {"Read", "Bash"}


def test_default_threshold_is_5000() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "cmd"}, "x" * 20001),  # ~5000 tokens
    )
    results = analyze_oversized(s)
    assert len(results) == 1


def test_pluggable_tokenizer() -> None:
    def custom_tokenizer(text: str) -> int:
        return len(text)  # 1 token = 1 character

    s = _session(
        _turn(0, "Bash", {"command": "cmd"}, "x" * 5001),
    )
    [r] = analyze_oversized(s, threshold=5000, tokenizer=custom_tokenizer)
    assert r.estimated_tokens == 5001


def test_unknown_command_when_missing() -> None:
    s = _session(
        _turn(0, "Bash", {}, "x" * 20001),  # No command provided
    )
    [r] = analyze_oversized(s)
    assert r.command == "unknown"


def test_harness_truncation_marker_sets_is_truncated() -> None:
    body = "x" * 20001 + "\n[output truncated: 500 lines omitted]"
    s = _session(_turn(0, "Bash", {"command": "npm test"}, body))
    [r] = analyze_oversized(s)
    assert r.is_truncated is True


def test_untruncated_output_not_marked_truncated() -> None:
    s = _session(_turn(0, "Bash", {"command": "npm test"}, "x" * 20001))
    [r] = analyze_oversized(s)
    assert r.is_truncated is False
