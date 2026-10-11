"""Edge cases for transcript parsing and CLI error handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcwa import jsonl as jsonl_module
from tcwa.cli import main
from tcwa.parse_claude import parse_claude_session
from tcwa.parse_codex import parse_codex_session
from tcwa.report import build_report

CODEX_FIXTURE = Path(__file__).parent / "fixtures" / "codex" / "basic.jsonl"


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _assistant(msg_id: str, blocks: list[dict], usage: dict | None = None) -> str:
    message: dict = {
        "id": msg_id,
        "role": "assistant",
        "model": "claude-sonnet-4",
        "content": blocks,
    }
    if usage is not None:
        message["usage"] = usage
    return json.dumps(
        {
            "type": "assistant",
            "sessionId": "edge",
            "timestamp": "2025-03-12T10:00:00Z",
            "message": message,
        }
    )


def _tool_use(tool_id: str, name: str, inp: dict) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": inp}


def _tool_result(tool_id: str, text: str) -> str:
    return json.dumps(
        {
            "type": "user",
            "sessionId": "edge",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}],
            },
        }
    )


def test_orphaned_tool_use_is_tolerated(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s.jsonl",
        [
            _assistant(
                "m1",
                [_tool_use("t1", "Bash", {"command": "ls"})],
                {"input_tokens": 10, "output_tokens": 5},
            )
        ],
    )
    report = build_report([parse_claude_session(f)])
    assert [s.tool for s in report.tool_spend] == ["Bash"]
    assert report.oversized == []


def test_unknown_record_types_are_ignored(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s.jsonl",
        [
            json.dumps({"type": "summary", "summary": "x"}),
            json.dumps({"type": "file-history-snapshot", "snapshot": {}}),
            _assistant("m1", [{"type": "text", "text": "hi"}], {"input_tokens": 1}),
        ],
    )
    session = parse_claude_session(f)
    assert len(session.turns) == 1
    assert session.usage.input_tokens == 1


def test_transcript_without_usage_reports_zero(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s.jsonl",
        [
            _assistant("m1", [_tool_use("t1", "Read", {"file_path": "a.py"})]),
            _tool_result("t1", "print(1)"),
        ],
    )
    report = build_report([parse_claude_session(f)])
    assert report.cost == 0.0
    assert report.cache_hit_ratio == 0.0


def test_malformed_lines_are_counted(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s.jsonl",
        [_assistant("m1", [], {"input_tokens": 1}), "{not json", "also broken}"],
    )
    session = parse_claude_session(f)
    assert session.malformed_lines == 2
    assert len(session.turns) == 1


@pytest.mark.parametrize("command", ["analyze", "sessions"])
def test_nonexistent_path_exits_2_with_message(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.jsonl"
    code = main([command, str(missing)])
    captured = capsys.readouterr()
    assert code == 2
    assert "does not exist" in captured.err
    assert str(missing) in captured.err


def test_malformed_lines_warn_on_stderr_and_keep_stdout_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write(
        tmp_path / "s.jsonl",
        [_assistant("m1", [], {"input_tokens": 1}), "{bad", "{worse"],
    )
    code = main(["analyze", str(f), "--format", "json"])
    captured = capsys.readouterr()
    assert code == 0
    assert "skipped 2 malformed line(s)" in captured.err
    assert json.loads(captured.out)["sessions"] == 1


def test_empty_file_yields_empty_report_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")
    code = main(["analyze", str(f)])
    captured = capsys.readouterr()
    assert code == 0
    assert "Sessions: 0" in captured.out
    assert "no transcript sessions found" in captured.err


def test_unrecognized_file_is_skipped_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write(tmp_path / "notes.jsonl", ['{"hello": "world"}'])
    code = main(["sessions", str(f)])
    captured = capsys.readouterr()
    assert code == 0
    assert "unrecognized transcript format" in captured.err


def test_unreadable_file_is_skipped_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_open = open

    def fake_open(path: object, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if Path(str(path)).name == "locked.jsonl":
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(jsonl_module, "open", fake_open, raising=False)
    _write(tmp_path / "locked.jsonl", [_assistant("m1", [], {"input_tokens": 1})])
    _write(tmp_path / "ok.jsonl", [_assistant("m2", [], {"input_tokens": 1})])

    code = main(["analyze", str(tmp_path), "--format", "json"])
    captured = capsys.readouterr()
    assert code == 0
    assert "cannot read file" in captured.err
    assert "locked.jsonl" in captured.err
    assert json.loads(captured.out)["sessions"] == 1


def test_codex_malformed_lines_are_counted(tmp_path: Path) -> None:
    f = tmp_path / "c.jsonl"
    f.write_text(CODEX_FIXTURE.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")
    session = parse_codex_session(f)
    assert session.malformed_lines == 1
    assert session.turns


def test_truncated_final_line_counts_as_malformed(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_text(_assistant("m1", [], {"input_tokens": 1}) + '\n{"type": "assi', encoding="utf-8")
    session = parse_claude_session(f)
    assert session.malformed_lines == 1
    assert len(session.turns) == 1
