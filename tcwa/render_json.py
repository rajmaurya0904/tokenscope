"""JSON report renderer: stable, versioned schema suitable for programmatic consumption."""

from __future__ import annotations

import json
from dataclasses import asdict

from tcwa.report import Report

SCHEMA_VERSION = "1.0"


def render_json(report: Report) -> str:
    """Render ``report`` as JSON with a stable, versioned schema.

    The JSON object includes:
    - schema_version: version string for backwards compatibility
    - sessions: session count
    - usage: token counts (input, output, cache_read, cache_creation)
    - cost: total cost in dollars
    - cache_hit_ratio: cache hit ratio as a decimal
    - tool_spend: list of per-tool aggregated spend
    - rereads: list of repeatedly read files
    - oversized: list of oversized tool outputs
    - cache_misses: list of cache misses
    - suggestions: list of actionable recommendations
    """
    output: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "sessions": report.session_count,
        "usage": asdict(report.usage),
        "cost": report.cost,
        "cache_hit_ratio": report.cache_hit_ratio,
        "tool_spend": [asdict(t) for t in report.tool_spend],
        "rereads": [asdict(r) for r in report.rereads],
        "oversized": [asdict(o) for o in report.oversized],
        "cache_misses": [asdict(m) for m in report.cache_misses],
        "suggestions": [asdict(s) for s in report.suggestions],
    }
    return json.dumps(output, indent=2) + "\n"
