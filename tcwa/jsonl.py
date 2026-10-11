"""Streaming JSONL reader with robust error handling."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any


class JSONLReader:
    """Streams JSONL files yielding parsed dicts, recording malformed lines."""

    def __init__(self, path: str | Path) -> None:
        """Initialize reader with file path.

        Args:
            path: Path to JSONL file (plain text UTF-8, gzip-less).
        """
        self.path = Path(path)
        self.warnings: list[dict[str, Any]] = []

    def read(self) -> Generator[dict[str, Any], None, None]:
        """Yield parsed dicts line by line, skip blanks, record malformed lines.

        Yields:
            Parsed JSON object as dict for each valid line.

        Warnings are recorded in self.warnings with line number and error details.
        """
        self.warnings = []
        line_number = 0

        with open(self.path, encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line_number += 1
                line = raw_line.rstrip("\n\r")

                if not line.strip():
                    continue

                try:
                    obj = json.loads(line)
                    yield obj
                except (json.JSONDecodeError, ValueError) as e:
                    self.warnings.append(
                        {
                            "line_number": line_number,
                            "error": str(e),
                            "content_preview": line[:100],
                        }
                    )
