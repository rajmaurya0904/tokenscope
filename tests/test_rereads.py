from tokenscope.analyzers.rereads import analyze_rereads
from tokenscope.models import Session, ToolCall, ToolResult, Turn


def _turn(i: int, name: str, inp: dict, out: str = "x" * 400) -> Turn:
    cid = f"c{i}"
    return Turn(index=i, tool_calls=[ToolCall(cid, name, inp)], tool_results=[ToolResult(cid, out)])


def _session(*turns: Turn) -> Session:
    return Session(id="s", provider="claude", turns=list(turns))


def test_three_reads_no_edit_flags_two_wasted() -> None:
    s = _session(*(_turn(i, "Read", {"file_path": "a.py"}) for i in range(3)))
    [r] = analyze_rereads(s)
    assert (r.path, r.reads, r.wasted_reads, r.wasted_tokens) == ("a.py", 3, 2, 200)


def test_read_edit_read_not_flagged() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "a.py"}),
        _turn(1, "Edit", {"file_path": "a.py"}, "ok"),
        _turn(2, "Read", {"file_path": "a.py"}),
    )
    assert analyze_rereads(s) == []


def test_path_normalization() -> None:
    s = _session(
        _turn(0, "Read", {"file_path": "./a.py"}),
        _turn(1, "Read", {"file_path": "a.py"}),
    )
    [r] = analyze_rereads(s)
    assert (r.path, r.wasted_reads) == ("a.py", 1)


def test_shell_reads_detected() -> None:
    s = _session(
        _turn(0, "Bash", {"command": "cat ./a.py"}),
        _turn(1, "Bash", {"command": "sed -n '1,20p' a.py"}),
        _turn(2, "Bash", {"command": "head -n 5 a.py"}),
        _turn(3, "Bash", {"command": "sed -i 's/a/b/' a.py"}),
    )
    [r] = analyze_rereads(s)
    assert (r.reads, r.wasted_reads) == (3, 2)
