"""Edge cases for transcript parsing and CLI error handling."""

from __future__ import annotations

import json
from pathlib import Path

from tcwa.parse_claude import parse_claude_session
from tcwa.report import build_report


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
