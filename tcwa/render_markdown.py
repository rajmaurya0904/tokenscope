"""Markdown report renderer: suitable for pasting into GitHub issues or pull requests."""

from __future__ import annotations

from tcwa.report import Report


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_money(amount: float) -> str:
    return f"${amount:,.4f}"


def _table_markdown(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a markdown table with headers and rows."""
    if not rows:
        return ["| (none) |"]

    lines = []
    header_line = "| " + " | ".join(headers) + " |"
    lines.append(header_line)

    separator_parts = [
        "-" * max(len(h), max(len(row[i]) for row in rows))
        for i, h in enumerate(headers)
    ]
    lines.append("|" + "|".join(separator_parts) + "|")

    for row in rows:
        row_line = "| " + " | ".join(row) + " |"
        lines.append(row_line)

    return lines


def render_markdown(report: Report, top_n: int = 10) -> str:
    """Render ``report`` as Markdown suitable for GitHub issues or pull requests.

    Each section is limited to the top ``top_n`` rows (findings are pre-sorted by severity).
    """
    lines: list[str] = []

    lines.append("# Cost & Waste Report")
    lines.append("")
    lines.append(f"**Sessions:** {report.session_count}")
    lines.append(f"**Total tokens:** {_fmt_int(report.usage.total_tokens)}")
    lines.append(f"**Total cost:** {_fmt_money(report.cost)}")
    lines.append(f"**Cache hit ratio:** {report.cache_hit_ratio:.1%}")
    lines.append("")

    lines.append("## Per-tool spend")
    lines.extend(
        _table_markdown(
            ["Tool", "Calls", "Output", "Carried", "Cost"],
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
        )
    )
    lines.append("")

    lines.append(f"## Repeated re-reads (top {top_n})")
    lines.extend(
        _table_markdown(
            ["Path", "Reads", "Wasted Reads", "Wasted Tokens"],
            [
                [r.path, _fmt_int(r.reads), _fmt_int(r.wasted_reads), _fmt_int(r.wasted_tokens)]
                for r in report.rereads[:top_n]
            ],
        )
    )
    lines.append("")

    lines.append(f"## Oversized outputs (top {top_n})")
    lines.extend(
        _table_markdown(
            ["Tool", "Command", "Tokens"],
            [[o.tool, o.command, _fmt_int(o.estimated_tokens)] for o in report.oversized[:top_n]],
        )
    )
    lines.append("")

    lines.append(f"## Cache misses (top {top_n})")
    lines.extend(
        _table_markdown(
            ["Turn", "Tokens", "Gap (s)", "Extra Cost"],
            [
                [
                    str(m.turn_index),
                    _fmt_int(m.cache_creation_tokens),
                    f"{m.gap_seconds:.1f}" if m.gap_seconds is not None else "-",
                    _fmt_money(m.extra_cost),
                ]
                for m in report.cache_misses[:top_n]
            ],
        )
    )
    lines.append("")

    lines.append(f"## Suggestions (top {top_n})")
    if not report.suggestions:
        lines.append("*(none)*")
    else:
        for s in report.suggestions[:top_n]:
            tokens = _fmt_int(s.estimated_tokens_saved)
            dollars = _fmt_money(s.estimated_dollars_saved)
            lines.append(f"- **[{s.category}]** {s.message} (~{tokens} tok, ~{dollars})")

    return "\n".join(lines) + "\n"
