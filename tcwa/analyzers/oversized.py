"""Oversized tool outputs: flag results above a configurable token threshold."""

from __future__ import annotations

from dataclasses import dataclass

from tcwa.analyzers.tool_spend import Tokenizer, estimate_tokens
from tcwa.models import Session, ToolCall


@dataclass
class OversizedResult:
    """A tool result that exceeded the token threshold."""

    tool: str
    command: str
    estimated_tokens: int
    is_truncated: bool = False
    has_no_limit: bool = False


def _get_command_for_tool(call: ToolCall) -> str:
    """Extract a human-readable command/identifier for a tool call."""
    if call.name == "Read":
        path = call.input.get("file_path") or call.input.get("path")
        return str(path) if path else "unknown"
    if call.name == "Bash":
        cmd = call.input.get("command") or call.input.get("cmd")
        if isinstance(cmd, list):
            return " ".join(str(c) for c in cmd)
        return str(cmd) if cmd else "unknown"
    if call.name == "Write":
        path = call.input.get("file_path") or call.input.get("path")
        return str(path) if path else "unknown"
    if call.name == "Edit":
        path = call.input.get("file_path") or call.input.get("path")
        return str(path) if path else "unknown"
    return "unknown"


def _check_no_limit_hint(call: ToolCall) -> bool:
    """Check if tool call was made without limit/offset constraints."""
    if call.name == "Read":
        limit = call.input.get("limit")
        offset = call.input.get("offset")
        return limit is None and offset is None
    return False


def analyze_oversized(
    session: Session,
    threshold: int = 5000,
    tokenizer: Tokenizer = estimate_tokens,
) -> list[OversizedResult]:
    """Flag tool results exceeding the token threshold, sorted by size descending.

    Args:
        session: The session to analyze.
        threshold: Token threshold; results above this are flagged (default 5000).
        tokenizer: Function to estimate tokens from content (default: chars/4 heuristic).

    Returns:
        List of flagged results, sorted by estimated_tokens descending.
    """
    results = []
    call_map: dict[str, ToolCall] = {}

    for turn in session.turns:
        for call in turn.tool_calls:
            call_map[call.id] = call

        for result in turn.tool_results:
            call = call_map.get(result.tool_call_id)
            if call is None:
                continue

            tokens = tokenizer(result.content)
            if tokens > threshold:
                cmd = _get_command_for_tool(call)
                has_no_limit = _check_no_limit_hint(call)
                oversized = OversizedResult(
                    tool=call.name,
                    command=cmd,
                    estimated_tokens=tokens,
                    has_no_limit=has_no_limit,
                )
                results.append(oversized)

    return sorted(results, key=lambda r: -r.estimated_tokens)
