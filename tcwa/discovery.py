"""Transcript format detection and session discovery."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from itertools import islice
from pathlib import Path

from tcwa.jsonl import JSONLReader

CLAUDE = "claude"
CODEX = "codex"

_SNIFF_RECORDS = 20
_CODEX_TYPES = {"session_meta", "turn_context", "response_item", "event_msg"}

DEFAULT_ROOTS = (Path("~/.claude/projects"), Path("~/.codex/sessions"))


class UnknownFormatError(ValueError):
    """Raised when a transcript is neither Claude Code nor Codex format."""


def detect_format(path: str | Path) -> str:
    """Return ``"claude"`` or ``"codex"`` by sniffing the first records of ``path``.

    Raises:
        UnknownFormatError: if no record matches a known transcript format.
    """
    reader = JSONLReader(path)
    for record in islice(reader.read(), _SNIFF_RECORDS):
        if not isinstance(record, dict):
            continue
        kind = record.get("type")
        if kind in _CODEX_TYPES and isinstance(record.get("payload"), dict):
            return CODEX
        if "sessionId" in record or (
            kind in ("user", "assistant") and isinstance(record.get("message"), dict)
        ):
            return CLAUDE
    raise UnknownFormatError(f"Unrecognized transcript format: {path}")


def _since_timestamp(since: date | datetime) -> float:
    if isinstance(since, datetime):
        return since.timestamp()
    return datetime.combine(since, time.min, tzinfo=UTC).timestamp()


def discover_sessions(
    path: str | Path | None = None,
    since: date | datetime | None = None,
) -> list[Path]:
    """Find transcript files under ``path`` (file or dir) or the default locations.

    Args:
        path: A JSONL file or a directory searched recursively. When ``None``, the
            default Claude Code and Codex locations are searched.
        since: If given, keep only files whose mtime is on or after this moment
            (naive dates are treated as UTC midnight).

    Returns:
        Sorted list of matching paths.
    """
    if path is None:
        roots = [r.expanduser() for r in DEFAULT_ROOTS]
    else:
        roots = [Path(path).expanduser()]

    found: list[Path] = []
    for root in roots:
        if root.is_file():
            found.append(root)
        elif root.is_dir():
            found.extend(p for p in root.rglob("*.jsonl") if p.is_file())

    if since is not None:
        cutoff = _since_timestamp(since)
        found = [p for p in found if p.stat().st_mtime >= cutoff]
    return sorted(found)
