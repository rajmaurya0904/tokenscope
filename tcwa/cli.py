"""The ``tcwa`` command-line interface: ``analyze`` and ``sessions`` subcommands."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from tcwa import __version__
from tcwa.aggregate import (
    GROUP_CHOICES,
    aggregate_sessions,
    aggregate_to_dict,
    render_aggregate_text,
)
from tcwa.discovery import UnknownFormatError, detect_format, discover_sessions
from tcwa.models import Session
from tcwa.parse_claude import parse_claude_session
from tcwa.parse_codex import parse_codex_session
from tcwa.pricing import ModelPricing, load_pricing_overrides, price_usage
from tcwa.render_json import render_json
from tcwa.render_markdown import render_markdown
from tcwa.render_text import DEFAULT_TOP_N, render_text
from tcwa.report import build_report

_PARSERS = {"claude": parse_claude_session, "codex": parse_codex_session}


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r} (expected YYYY-MM-DD)"
        ) from exc


def _resolve_paths(paths: Sequence[str], since: date | None) -> list[Path]:
    """Discover transcript files from ``paths`` (or the default roots when empty)."""
    if not paths:
        return discover_sessions(since=since)
    seen: set[Path] = set()
    found: list[Path] = []
    for raw in paths:
        for f in discover_sessions(raw, since=since):
            if f not in seen:
                seen.add(f)
                found.append(f)
    return sorted(found)


def _load_session(path: Path) -> Session | None:
    try:
        fmt = detect_format(path)
    except UnknownFormatError:
        return None
    return _PARSERS[fmt](path)


def _load_sessions(paths: Sequence[str], since: date | None) -> list[Session]:
    sessions = []
    for f in _resolve_paths(paths, since):
        session = _load_session(f)
        if session is not None:
            sessions.append(session)
    return sessions


def _load_overrides(prices: str | None) -> dict[str, ModelPricing] | None:
    return load_pricing_overrides(prices) if prices else None


def cmd_analyze(args: argparse.Namespace) -> int:
    sessions = _load_sessions(args.paths, args.since)
    overrides = _load_overrides(args.prices)
    report = build_report(sessions, oversized_threshold=args.threshold, overrides=overrides)
    if args.min_savings > 0:
        report.suggestions = [
            s for s in report.suggestions if s.estimated_dollars_saved >= args.min_savings
        ]

    agg = None
    if args.group_by:
        agg = aggregate_sessions(
            sessions,
            group_by=args.group_by,
            oversized_threshold=args.threshold,
            overrides=overrides,
        )

    if args.format == "json":
        output = render_json(report)
        if agg is not None:
            data = json.loads(output)
            data["aggregate"] = aggregate_to_dict(agg)
            output = json.dumps(data, indent=2) + "\n"
    elif args.format == "markdown":
        output = render_markdown(report, top_n=args.top)
        if agg is not None:
            output += "\n" + render_aggregate_text(agg, top_n=args.top)
    else:
        output = render_text(report, top_n=args.top)
        if agg is not None:
            output += "\n" + render_aggregate_text(agg, top_n=args.top)
    sys.stdout.write(output)
    return 0


def _fmt_money(amount: float) -> str:
    return f"${amount:,.4f}"


def _session_rows(paths: Sequence[str], since: date | None, overrides: dict | None) -> list[dict]:
    rows = []
    for f in _resolve_paths(paths, since):
        session = _load_session(f)
        if session is None:
            continue
        cost = sum(price_usage(t.usage, t.model or "", overrides).amount for t in session.turns)
        timestamps = [t.timestamp for t in session.turns if t.timestamp is not None]
        earliest = min(timestamps) if timestamps else None
        rows.append(
            {
                "id": session.id,
                "provider": session.provider,
                "path": str(f),
                "date": earliest.isoformat() if earliest else None,
                "size_bytes": f.stat().st_size,
                "cost": cost,
            }
        )
    return rows


def _render_sessions_text(rows: list[dict]) -> str:
    headers = ["ID", "PROVIDER", "DATE", "SIZE", "COST"]
    if not rows:
        return "\n".join([" ".join(headers), "  (none)"]) + "\n"
    cells = [
        [r["id"], r["provider"], r["date"] or "-", str(r["size_bytes"]), _fmt_money(r["cost"])]
        for r in rows
    ]
    widths = [max(len(h), *(len(row[i]) for row in cells)) for i, h in enumerate(headers)]
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        for row in [headers, *cells]
    ]
    return "\n".join(lines) + "\n"


def cmd_sessions(args: argparse.Namespace) -> int:
    overrides = _load_overrides(args.prices)
    rows = _session_rows(args.paths, args.since, overrides)
    if args.format == "json":
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        sys.stdout.write(_render_sessions_text(rows))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcwa",
        description="Analyze agent session transcripts for token cost and waste.",
    )
    parser.add_argument("--version", action="version", version=f"tcwa {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    analyze_p = subparsers.add_parser(
        "analyze", help="Parse transcripts and print a full cost/waste report"
    )
    analyze_p.add_argument(
        "paths",
        nargs="*",
        help="Transcript files or directories (default: the standard Claude Code/Codex locations)",
    )
    analyze_p.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text", help="Output format"
    )
    analyze_p.add_argument(
        "--top", type=int, default=DEFAULT_TOP_N, help="Limit each section to its top N findings"
    )
    analyze_p.add_argument(
        "--since",
        type=_parse_date,
        default=None,
        help="Only include sessions modified since this date (YYYY-MM-DD)",
    )
    analyze_p.add_argument(
        "--threshold",
        type=int,
        default=5000,
        help="Token threshold for flagging oversized tool outputs",
    )
    analyze_p.add_argument(
        "--prices", default=None, help="Path to a JSON file of per-model pricing overrides"
    )
    analyze_p.add_argument(
        "--min-savings",
        type=float,
        default=0.0,
        dest="min_savings",
        help="Only show suggestions estimated to save at least this many dollars",
    )
    analyze_p.add_argument(
        "--group-by",
        choices=GROUP_CHOICES,
        default=None,
        dest="group_by",
        help="Also rank sessions by cost and merge findings into project or day buckets",
    )
    analyze_p.set_defaults(func=cmd_analyze)

    sessions_p = subparsers.add_parser(
        "sessions", help="List discovered transcripts with their date, size and cost"
    )
    sessions_p.add_argument(
        "paths",
        nargs="*",
        help="Transcript files or directories (default: the standard Claude Code/Codex locations)",
    )
    sessions_p.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    sessions_p.add_argument(
        "--since",
        type=_parse_date,
        default=None,
        help="Only include sessions modified since this date (YYYY-MM-DD)",
    )
    sessions_p.add_argument(
        "--prices", default=None, help="Path to a JSON file of per-model pricing overrides"
    )
    sessions_p.set_defaults(func=cmd_sessions)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
