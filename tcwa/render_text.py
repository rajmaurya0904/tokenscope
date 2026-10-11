"""Plain-text report renderer: aligned tables, a top-N limit, and TTY-only color."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from tcwa.report import Report

DEFAULT_TOP_N = 10

_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"


def _use_color(color: bool | None) -> bool:
    if color is not None:
        return color
    return sys.stdout.isatty()


def _bold(text: str, color: bool) -> str:
    return f"{_BOLD}{text}{_RESET}" if color else text


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_money(amount: float) -> str:
    return f"${amount:,.4f}"


def _table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], aligns: Sequence[str]
) -> list[str]:
    """Render an aligned plain-text table; ``aligns`` is ``"l"``/``"r"`` per column."""
    if not rows:
        return ["  (none)"]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]

    def fmt_row(cells: Sequence[str]) -> str:
        parts = [
            cell.rjust(widths[i]) if align == "r" else cell.ljust(widths[i])
            for i, (cell, align) in enumerate(zip(cells, aligns, strict=True))
        ]
        return "  ".join(parts).rstrip()

    return [fmt_row(headers), *(fmt_row(row) for row in rows)]


def render_text(report: Report, top_n: int = DEFAULT_TOP_N, color: bool | None = None) -> str:
    """Render ``report`` as plain text: a totals header plus one aligned table per finding type.

    Each section is limited to the top ``top_n`` rows (findings are pre-sorted by
    severity). Color is applied only when ``color`` is True, or left unset and
    stdout is a TTY -- there is no color library dependency.
    """
    use_color = _use_color(color)
    lines: list[str] = []

    lines.append(_bold("=== Cost & Waste Report ===", use_color))
    lines.append(f"Sessions: {report.session_count}")
    lines.append(f"Total tokens: {_fmt_int(report.usage.total_tokens)}")
    lines.append(f"Total cost: {_fmt_money(report.cost)}")
    lines.append(f"Cache hit ratio: {report.cache_hit_ratio:.1%}")
    lines.append("")

    lines.append(_bold("-- Per-tool spend --", use_color))
    lines.extend(
        _table(
            ["TOOL", "CALLS", "OUTPUT", "CARRIED", "COST"],
            [
                [
                    s.tool,
                    _fmt_int(s.calls),
                    _fmt_int(s.output_tokens),
                    _fmt_int(s.carried_tokens),
                    _fmt_money(s.cost),
                ]
                for s in report.tool_spend[:top_n]
            ],
            ["l", "r", "r", "r", "r"],
        )
    )
    lines.append("")

    lines.append(_bold(f"-- Repeated re-reads (top {top_n}) --", use_color))
    lines.extend(
        _table(
            ["PATH", "READS", "WASTED READS", "WASTED TOKENS"],
            [
                [r.path, _fmt_int(r.reads), _fmt_int(r.wasted_reads), _fmt_int(r.wasted_tokens)]
                for r in report.rereads[:top_n]
            ],
            ["l", "r", "r", "r"],
        )
    )
    lines.append("")

    lines.append(_bold(f"-- Oversized outputs (top {top_n}) --", use_color))
    lines.extend(
        _table(
            ["TOOL", "COMMAND", "TOKENS"],
            [[o.tool, o.command, _fmt_int(o.estimated_tokens)] for o in report.oversized[:top_n]],
            ["l", "l", "r"],
        )
    )
    lines.append("")

    lines.append(_bold(f"-- Cache misses (top {top_n}) --", use_color))
    lines.extend(
        _table(
            ["TURN", "TOKENS", "GAP (s)", "EXTRA COST"],
            [
                [
                    str(m.turn_index),
                    _fmt_int(m.cache_creation_tokens),
                    f"{m.gap_seconds:.1f}" if m.gap_seconds is not None else "-",
                    _fmt_money(m.extra_cost),
                ]
                for m in report.cache_misses[:top_n]
            ],
            ["r", "r", "r", "r"],
        )
    )
    lines.append("")

    lines.append(_bold(f"-- Suggestions (top {top_n}) --", use_color))
    if not report.suggestions:
        lines.append("  (none)")
    else:
        for s in report.suggestions[:top_n]:
            tokens = _fmt_int(s.estimated_tokens_saved)
            dollars = _fmt_money(s.estimated_dollars_saved)
            lines.append(f"[{s.category}] {s.message} (~{tokens} tok, ~{dollars})")

    return "\n".join(lines) + "\n"
