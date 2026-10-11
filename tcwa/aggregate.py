"""Cross-session aggregation: totals, session ranking, and project/day grouping."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from tcwa.analyzers.oversized import OversizedResult, analyze_oversized
from tcwa.analyzers.rereads import FileReread, analyze_rereads
from tcwa.analyzers.tool_spend import Tokenizer, estimate_tokens
from tcwa.models import Session, Usage
from tcwa.pricing import ModelPricing, price_usage

GROUP_PROJECT = "project"
GROUP_DAY = "day"
GROUP_CHOICES = (GROUP_PROJECT, GROUP_DAY)


@dataclass
class SessionTotal:
    """One session's identity and totals, used to rank the most expensive sessions."""

    id: str
    project: str
    day: str | None
    usage: Usage
    cost: float


@dataclass
class Group:
    """Aggregated totals and merged findings for one project or day bucket."""

    key: str
    session_count: int
    usage: Usage
    cost: float
    rereads: list[FileReread] = field(default_factory=list)
    oversized: list[OversizedResult] = field(default_factory=list)


@dataclass
class AggregateReport:
    """Cross-session totals, sessions ranked by cost, and group-by buckets."""

    group_by: str
    session_count: int
    usage: Usage
    cost: float
    sessions: list[SessionTotal] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)


def session_project(session: Session) -> str:
    """The project a session belongs to: its transcript file's parent directory name."""
    if not session.path:
        return "unknown"
    return Path(session.path).parent.name or "unknown"


def session_day(session: Session) -> str | None:
    """The ISO date of a session's earliest turn timestamp, or None if it has none."""
    timestamps = [t.timestamp for t in session.turns if t.timestamp is not None]
    return min(timestamps).date().isoformat() if timestamps else None


def _session_cost(session: Session, overrides: dict[str, ModelPricing] | None) -> float:
    return sum(price_usage(t.usage, t.model or "", overrides).amount for t in session.turns)


def _merge_rereads(all_rereads: list[FileReread]) -> list[FileReread]:
    merged: dict[str, FileReread] = {}
    for r in all_rereads:
        entry = merged.setdefault(r.path, FileReread(r.path))
        entry.reads += r.reads
        entry.wasted_reads += r.wasted_reads
        entry.wasted_tokens += r.wasted_tokens
    return sorted(merged.values(), key=lambda r: (-r.wasted_tokens, r.path))


def _group_key(total: SessionTotal, group_by: str) -> str:
    if group_by == GROUP_DAY:
        return total.day or "unknown"
    return total.project


def aggregate_sessions(
    sessions: list[Session],
    group_by: str = GROUP_PROJECT,
    oversized_threshold: int = 5000,
    tokenizer: Tokenizer = estimate_tokens,
    overrides: dict[str, ModelPricing] | None = None,
) -> AggregateReport:
    """Aggregate ``sessions``: totals, sessions ranked by cost, and project/day buckets.

    Each session is bucketed by ``group_by`` (``"project"``, from its transcript's
    parent directory, or ``"day"``, from its earliest turn's date). Within a bucket,
    repeated-read and oversized findings are merged by path/command -- the same way
    ``build_report`` merges them across an entire session set -- so recurring waste
    patterns surface per project or day.
    """
    if group_by not in GROUP_CHOICES:
        raise ValueError(f"group_by must be one of {GROUP_CHOICES}, got {group_by!r}")

    totals: list[SessionTotal] = []
    buckets: dict[str, list[Session]] = {}
    usage = Usage()
    cost = 0.0

    for session in sessions:
        session_cost = _session_cost(session, overrides)
        total = SessionTotal(
            id=session.id,
            project=session_project(session),
            day=session_day(session),
            usage=session.usage,
            cost=session_cost,
        )
        totals.append(total)
        usage = usage + session.usage
        cost += session_cost
        buckets.setdefault(_group_key(total, group_by), []).append(session)

    ranked = sorted(totals, key=lambda t: (-t.cost, t.id))

    groups: list[Group] = []
    for key, bucket_sessions in buckets.items():
        group_usage = Usage()
        group_cost = 0.0
        rereads: list[FileReread] = []
        oversized: list[OversizedResult] = []
        for session in bucket_sessions:
            group_usage = group_usage + session.usage
            group_cost += _session_cost(session, overrides)
            rereads.extend(analyze_rereads(session, tokenizer))
            oversized.extend(analyze_oversized(session, oversized_threshold, tokenizer))
        groups.append(
            Group(
                key=key,
                session_count=len(bucket_sessions),
                usage=group_usage,
                cost=group_cost,
                rereads=_merge_rereads(rereads),
                oversized=sorted(oversized, key=lambda r: -r.estimated_tokens),
            )
        )
    groups.sort(key=lambda g: (-g.cost, g.key))

    return AggregateReport(
        group_by=group_by,
        session_count=len(sessions),
        usage=usage,
        cost=cost,
        sessions=ranked,
        groups=groups,
    )


def aggregate_to_dict(agg: AggregateReport) -> dict:
    """Render ``agg`` as a plain dict of JSON-serializable values."""
    return {
        "group_by": agg.group_by,
        "session_count": agg.session_count,
        "usage": asdict(agg.usage),
        "cost": agg.cost,
        "sessions": [asdict(t) for t in agg.sessions],
        "groups": [
            {
                "key": g.key,
                "session_count": g.session_count,
                "usage": asdict(g.usage),
                "cost": g.cost,
                "rereads": [asdict(r) for r in g.rereads],
                "oversized": [asdict(o) for o in g.oversized],
            }
            for g in agg.groups
        ],
    }


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_money(amount: float) -> str:
    return f"${amount:,.4f}"


def render_aggregate_text(agg: AggregateReport, top_n: int = 10) -> str:
    """Render ``agg`` as plain text: ranked sessions, then one block per group."""
    lines: list[str] = []
    lines.append(f"=== Grouped by {agg.group_by} ===")
    lines.append(f"Sessions: {agg.session_count}")
    lines.append(f"Total tokens: {_fmt_int(agg.usage.total_tokens)}")
    lines.append(f"Total cost: {_fmt_money(agg.cost)}")
    lines.append("")

    lines.append(f"-- Sessions ranked by cost (top {top_n}) --")
    if not agg.sessions:
        lines.append("  (none)")
    for total in agg.sessions[:top_n]:
        lines.append(f"  {total.id}  {total.project}  {total.day or '-'}  {_fmt_money(total.cost)}")
    lines.append("")

    for group in agg.groups:
        lines.append(f"-- {agg.group_by}: {group.key} ({group.session_count} sessions) --")
        lines.append(
            f"  Tokens: {_fmt_int(group.usage.total_tokens)}  Cost: {_fmt_money(group.cost)}"
        )
        for r in group.rereads[:top_n]:
            lines.append(f"  reread    {r.path}  wasted_tokens={_fmt_int(r.wasted_tokens)}")
        for o in group.oversized[:top_n]:
            lines.append(f"  oversized {o.tool} {o.command}  tokens={_fmt_int(o.estimated_tokens)}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
