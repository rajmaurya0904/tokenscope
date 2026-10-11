"""Parse Claude Code session JSONL transcripts into the normalized Session model."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tcwa.jsonl import JSONLReader
from tcwa.models import Session, ToolCall, ToolResult, Turn, Usage


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_usage(raw: Any) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    return Usage(
        input_tokens=raw.get("input_tokens") or 0,
        output_tokens=raw.get("output_tokens") or 0,
        cache_read_tokens=raw.get("cache_read_input_tokens") or 0,
        cache_creation_tokens=raw.get("cache_creation_input_tokens") or 0,
    )


def _max_usage(a: Usage, b: Usage) -> Usage:
    return Usage(
        max(a.input_tokens, b.input_tokens),
        max(a.output_tokens, b.output_tokens),
        max(a.cache_read_tokens, b.cache_read_tokens),
        max(a.cache_creation_tokens, b.cache_creation_tokens),
    )


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def parse_claude_session(path: str | Path) -> Session:
    """Parse a Claude Code JSONL transcript.

    One Turn is produced per distinct assistant ``message.id``. Streamed entries
    repeating an id are merged: usage is not summed (the largest count per field
    wins) and tool calls are de-duplicated by id. Tool results are attached to
    the turn holding the matching ``tool_use``.
    """
    path = Path(path)
    session = Session(id=path.stem, provider="claude", path=str(path))
    turns_by_msg: dict[str, Turn] = {}
    turn_by_tool: dict[str, Turn] = {}

    for entry in JSONLReader(path).read():
        if not isinstance(entry, dict):
            continue
        if entry.get("sessionId"):
            session.id = entry["sessionId"]
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")

        if entry.get("type") == "assistant":
            msg_id = message.get("id")
            turn = turns_by_msg.get(msg_id) if msg_id else None
            if turn is None:
                turn = Turn(
                    index=len(session.turns),
                    timestamp=_parse_timestamp(entry.get("timestamp")),
                    model=message.get("model"),
                    is_sidechain=bool(entry.get("isSidechain")),
                )
                session.turns.append(turn)
                if msg_id:
                    turns_by_msg[msg_id] = turn
            turn.model = turn.model or message.get("model")
            turn.usage = _max_usage(turn.usage, _parse_usage(message.get("usage")))
            for block in content if isinstance(content, list) else []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("id") not in turn_by_tool
                ):
                    turn.tool_calls.append(
                        ToolCall(
                            id=block["id"],
                            name=block.get("name", ""),
                            input=block.get("input") or {},
                        )
                    )
                    turn_by_tool[block["id"]] = turn
        elif entry.get("type") == "user" and isinstance(content, list):
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                turn = turn_by_tool.get(block.get("tool_use_id"))
                if turn is not None:
                    turn.tool_results.append(
                        ToolResult(
                            tool_call_id=block["tool_use_id"],
                            content=_result_text(block.get("content")),
                            is_error=bool(block.get("is_error")),
                        )
                    )
    return session
