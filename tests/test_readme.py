"""Tests for README.md content and completeness."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _get_readme_content() -> str:
    """Read the README.md file."""
    readme_path = Path(__file__).parent.parent / "README.md"
    return readme_path.read_text(encoding="utf-8")


def _extract_headings(text: str) -> set[str]:
    """Extract heading text from markdown."""
    headings = set()
    for match in re.finditer(r"^#+\s+(.+?)$", text, re.MULTILINE):
        headings.add(match.group(1).strip())
    return headings


def test_readme_has_required_headings() -> None:
    """Verify README has all required section headings."""
    content = _get_readme_content()
    headings = _extract_headings(content)

    required = {"Install", "Usage", "How it works", "Limitations", "Development"}
    missing = required - headings

    assert not missing, f"README missing required headings: {missing}"


def test_readme_mentions_analyze_flags() -> None:
    """Verify README mentions every flag from tokenscope analyze --help."""
    content = _get_readme_content()

    # Expected flags based on the CLI definition (from cli.py)
    expected_flags = {
        "format",
        "top",
        "since",
        "threshold",
        "prices",
        "min-savings",
        "group-by",
    }

    # Check each flag is mentioned in README
    missing_flags = []
    for flag in sorted(expected_flags):
        # Replace hyphens with either hyphens or underscores in the search
        # (README might use either style when describing the flag)
        flag_pattern = re.escape(flag).replace(r"\-", "[-_]")
        if not re.search(flag_pattern, content, re.IGNORECASE):
            missing_flags.append(flag)

    assert not missing_flags, (
        f"README does not mention these CLI flags: {missing_flags}\n"
        f"Expected flags: {sorted(expected_flags)}"
    )


def test_readme_has_example_output() -> None:
    """Verify README contains sample output."""
    content = _get_readme_content()

    # Check for key sections of example output
    assert "Cost & Waste Report" in content
    assert "Per-tool spend" in content
    assert "Repeated re-reads" in content
    assert "Oversized outputs" in content
    assert "Cache misses" in content
    assert "Suggestions" in content


def test_readme_has_privacy_note() -> None:
    """Verify README states the tool is local-only and uploads nothing."""
    content = _get_readme_content()

    assert "local" in content.lower()
    assert "never" in content.lower() and "upload" in content.lower()


def test_readme_limitations_cover_pricing_and_token_estimate() -> None:
    """Verify Limitations is honest about the pricing table and chars/4 estimate."""
    content = _get_readme_content()
    limitations = content.split("## Limitations", 1)[1].split("## ", 1)[0]

    assert "chars/4" in limitations
    assert "heuristic" in limitations
    assert "pricing table" in limitations


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
