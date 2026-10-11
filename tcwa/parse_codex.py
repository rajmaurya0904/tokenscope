"""Parse Codex CLI rollout JSONL transcripts into the normalized Session model."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tcwa.jsonl import JSONLReader
from tcwa.models import Session, ToolCall, ToolResult, Turn, Usage

_SHELL_TOOLS = {"shell", "local_shell", "shell_command", "container.exec", "exec_command"}
_READ_TOOLS = {"read", "read_file"}
_CALL_TYPES = {"function_call", "custom_tool_call", "local_shell_call"}
_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _command_text(args: dict[str, Any]) -> str:
    cmd = args.get("command") or args.get("cmd")
    if isinstance(cmd, list):
        return " ".join(str(c) for c in cmd)
    return cmd if isinstance(cmd, str) else ""


def _normalize_tool(name: str, args: dict[str, Any]) -> str:
    """Map Codex tool names onto the Claude-style names used by the model."""
    if name == "apply_patch":
        return "Edit"
    if name in _READ_TOOLS:
        return "Read"
    if name in _SHELL_TOOLS:
        return "Edit" if "apply_patch" in _command_text(args) else "Bash"
    return name


def _cumulative(raw: Any) -> Usage | None:
    """Convert a Codex ``total_token_usage`` dict to Usage.

    Codex ``input_tokens`` includes cached tokens and ``output_tokens`` includes
    reasoning tokens, so cached input is split out to keep the sum equal to
    ``total_tokens``.
    """
    if not isinstance(raw, dict):
        return None
    cached = raw.get("cached_input_tokens") or 0
    return Usage(
        input_tokens=(raw.get("input_tokens") or 0) - cached,
        output_tokens=raw.get("output_tokens") or 0,
        cache_read_tokens=cached,
    )


def _sub(a: Usage, b: Usage) -> Usage:
    return Usage(
        a.input_tokens - b.input_tokens,
        a.output_tokens - b.output_tokens,
        a.cache_read_tokens - b.cache_read_tokens,
        a.cache_creation_tokens - b.cache_creation_tokens,
    )


def _output_text(raw: Any) -> tuple[str, bool]:
    """Return (text, is_error); outputs may be JSON like {"output": ..., "metadata": ...}."""
    if isinstance(raw, dict):
        raw = raw.get("content") or raw.get("output") or ""
    if not isinstance(raw, str):
        return "", False
    try:
        data = json.loads(raw)
    except ValueError:
        return raw, False
    if isinstance(data, dict) and "output" in data:
        meta = data.get("metadata")
        exit_code = meta.get("exit_code") if isinstance(meta, dict) else None
        return str(data["output"]), bool(exit_code)
    return raw, False


def parse_codex_session(path: str | Path) -> Session:
    """Parse a Codex CLI rollout JSONL file.

    Response items accumulate into the current Turn; each ``token_count`` event
    closes it, attributing the delta of the cumulative ``total_token_usage`` since
    the previous event. Function call outputs attach to the turn holding the
    matching ``call_id``.
    """
    path = Path(path)
    session = Session(id=path.stem, provider="codex", path=str(path))
    turn_by_call: dict[str, Turn] = {}
    model: str | None = None
    current: Turn | None = None
    previous = Usage()

    def open_turn(timestamp: datetime | None) -> Turn:
        turn = Turn(index=len(session.turns), timestamp=timestamp, model=model)
        session.turns.append(turn)
        return turn

    for entry in JSONLReader(path).read():
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        kind = entry.get("type")
        ptype = payload.get("type")

        if kind == "session_meta":
            session.id = payload.get("id") or session.id
        elif kind == "turn_context":
            model = payload.get("model") or model
        elif kind == "response_item":
            if ptype in _CALL_TYPES:
                call_id = payload.get("call_id") or payload.get("id")
                if not call_id or call_id in turn_by_call:
                    continue
                raw_args = payload.get("arguments")
                if raw_args is None:
                    raw_args = payload.get("input") or payload.get("action")
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except ValueError:
                        raw_args = {"input": raw_args}
                args = raw_args if isinstance(raw_args, dict) else {}
                name = payload.get("name") or "shell"
                current = current or open_turn(_parse_timestamp(entry.get("timestamp")))
                current.tool_calls.append(
                    ToolCall(id=call_id, name=_normalize_tool(name, args), input=args)
                )
                turn_by_call[call_id] = current
            elif ptype in _OUTPUT_TYPES:
                turn = turn_by_call.get(payload.get("call_id"))
                if turn is not None:
                    text, is_error = _output_text(payload.get("output"))
                    turn.tool_results.append(
                        ToolResult(payload["call_id"], content=text, is_error=is_error)
                    )
            elif ptype in ("message", "reasoning") and payload.get("role", "assistant") != "user":
                current = current or open_turn(_parse_timestamp(entry.get("timestamp")))
        elif kind == "event_msg" and ptype == "token_count":
            info = payload.get("info")
            total = _cumulative(info.get("total_token_usage")) if isinstance(info, dict) else None
            if total is None or total == previous:
                continue
            current = current or open_turn(_parse_timestamp(entry.get("timestamp")))
            current.usage = current.usage + _sub(total, previous)
            previous = total
            current = None
    return session
