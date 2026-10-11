"""Repeated file re-reads: reads with no intervening Edit/Write are wasted."""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass
from typing import Any

from tcwa.analyzers.tool_spend import Tokenizer, estimate_tokens
from tcwa.models import Session, ToolCall

_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_READ_CMDS = {"cat", "head", "tail", "sed", "nl", "less", "more"}
_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)


@dataclass
class FileReread:
    """A file read more than once in a session."""

    path: str
    reads: int = 0
    wasted_reads: int = 0
    wasted_tokens: int = 0


def normalize_path(path: str) -> str:
    """Collapse ``./a.py`` and ``a.py`` (and ``x/../a.py``) to one key."""
    return posixpath.normpath(path)


def _command_text(args: dict[str, Any]) -> str:
    cmd = args.get("command") or args.get("cmd")
    if isinstance(cmd, list):
        return " ".join(str(c) for c in cmd)
    return cmd if isinstance(cmd, str) else ""


def _command_read_paths(command: str) -> list[str]:
    """File operands of a simple cat/head/tail/sed -n style command."""
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    if words[:2] in (["bash", "-lc"], ["bash", "-c"], ["sh", "-c"]) and len(words) > 2:
        return _command_read_paths(words[2])
    if not words or words[0] not in _READ_CMDS:
        return []
    cmd, rest = words[0], words[1:]
    if any(w in ("|", "&&", ";", ">", ">>") for w in rest):
        return []
    if cmd == "sed":
        if any(w == "-i" or w.startswith("-i") or w == "--in-place" for w in rest):
            return []
        operands = [w for w in rest if not w.startswith("-")]
        return operands[1:]  # first operand is the script
    operands: list[str] = []
    skip = False
    for w in rest:
        if skip:
            skip = False
        elif w in ("-n", "-c"):
            skip = True
        elif not w.startswith("-") or w == "-":
            operands.append(w)
    return [o for o in operands if o != "-"]


def _read_paths(call: ToolCall) -> list[str]:
    if call.name == "Read":
        path = call.input.get("file_path") or call.input.get("path")
        return [path] if isinstance(path, str) and path else []
    if call.name == "Bash":
        return _command_read_paths(_command_text(call.input))
    return []


def _edit_paths(call: ToolCall) -> list[str]:
    if call.name not in _EDIT_TOOLS:
        return []
    path = call.input.get("file_path") or call.input.get("path")
    if isinstance(path, str) and path:
        return [path]
    return _PATCH_FILE.findall(_command_text(call.input))


def analyze_rereads(session: Session, tokenizer: Tokenizer = estimate_tokens) -> list[FileReread]:
    """Flag files read repeatedly; only reads with no edit since the last read are wasted.

    Sorted by descending wasted tokens. Files with no wasted read are omitted.
    """
    stats: dict[str, FileReread] = {}
    fresh: set[str] = set()  # read since last modification
    for turn in session.turns:
        content = {r.tool_call_id: r.content for r in turn.tool_results}
        for call in turn.tool_calls:
            for path in _edit_paths(call):
                fresh.discard(normalize_path(path))
            tokens = tokenizer(content.get(call.id, ""))
            for path in _read_paths(call):
                key = normalize_path(path)
                entry = stats.setdefault(key, FileReread(key))
                entry.reads += 1
                if key in fresh:
                    entry.wasted_reads += 1
                    entry.wasted_tokens += tokens
                fresh.add(key)
    flagged = [s for s in stats.values() if s.wasted_reads]
    return sorted(flagged, key=lambda s: (-s.wasted_tokens, s.path))
