"""Provider-neutral event model emitted by the Claude Code and Codex parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Usage:
    """Token counts for a single turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def __add__(self, other: Usage) -> Usage:
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
        )


@dataclass
class ToolCall:
    """A tool invocation requested by the assistant."""

    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The output returned for a tool call."""

    tool_call_id: str
    content: str = ""
    is_error: bool = False


@dataclass
class Turn:
    """One assistant turn: its usage, tool calls, and the results that came back."""

    index: int
    role: str = "assistant"
    timestamp: datetime | None = None
    model: str | None = None
    is_sidechain: bool = False
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class Session:
    """A full transcript from one provider."""

    id: str
    provider: str
    turns: list[Turn] = field(default_factory=list)
    path: str | None = None

    @property
    def usage(self) -> Usage:
        total = Usage()
        for turn in self.turns:
            total = total + turn.usage
        return total
