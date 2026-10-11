"""Report aggregation: combine every analyzer's findings for one or many sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from tcwa.analyzers.cache import DEFAULT_TTL, CacheMiss, analyze_cache
from tcwa.analyzers.oversized import OversizedResult, analyze_oversized
from tcwa.analyzers.rereads import FileReread, analyze_rereads
from tcwa.analyzers.tool_spend import Tokenizer, ToolSpend, analyze_tool_spend, estimate_tokens
from tcwa.models import Session, Usage
from tcwa.pricing import ModelPricing, price_usage
from tcwa.suggestions import Suggestion, generate_suggestions


@dataclass
class Report:
    """Aggregated totals and findings for one or many sessions."""

    session_count: int
    usage: Usage
    cost: float
    tool_spend: list[ToolSpend] = field(default_factory=list)
    rereads: list[FileReread] = field(default_factory=list)
    oversized: list[OversizedResult] = field(default_factory=list)
    cache_misses: list[CacheMiss] = field(default_factory=list)
    cache_hit_ratio: float = 0.0
    suggestions: list[Suggestion] = field(default_factory=list)


def _merge_tool_spend(all_spend: list[ToolSpend]) -> list[ToolSpend]:
    merged: dict[str, ToolSpend] = {}
    for s in all_spend:
        entry = merged.setdefault(s.tool, ToolSpend(s.tool))
        entry.calls += s.calls
        entry.output_tokens += s.output_tokens
        entry.carried_tokens += s.carried_tokens
        entry.cost += s.cost
    return sorted(merged.values(), key=lambda s: (-s.cost, s.tool))


def _merge_rereads(all_rereads: list[FileReread]) -> list[FileReread]:
    merged: dict[str, FileReread] = {}
    for r in all_rereads:
        entry = merged.setdefault(r.path, FileReread(r.path))
        entry.reads += r.reads
        entry.wasted_reads += r.wasted_reads
        entry.wasted_tokens += r.wasted_tokens
    return sorted(merged.values(), key=lambda r: (-r.wasted_tokens, r.path))


def build_report(
    sessions: list[Session],
    oversized_threshold: int = 5000,
    cache_min_tokens: int = 1000,
    cache_ttl: timedelta = DEFAULT_TTL,
    tokenizer: Tokenizer = estimate_tokens,
    overrides: dict[str, ModelPricing] | None = None,
) -> Report:
    """Aggregate every analyzer's findings across ``sessions`` into one Report.

    Per-tool spend and re-read stats are merged across sessions (summed by tool
    or path); oversized outputs and cache misses are concatenated and re-sorted,
    since each finding is already tied to a specific turn.
    """
    usage = Usage()
    cost = 0.0
    tool_spend: list[ToolSpend] = []
    rereads: list[FileReread] = []
    oversized: list[OversizedResult] = []
    cache_misses: list[CacheMiss] = []

    for session in sessions:
        usage = usage + session.usage
        for turn in session.turns:
            cost += price_usage(turn.usage, turn.model or "", overrides).amount
        tool_spend.extend(analyze_tool_spend(session, tokenizer, overrides))
        rereads.extend(analyze_rereads(session, tokenizer))
        oversized.extend(analyze_oversized(session, oversized_threshold, tokenizer))
        cache_misses.extend(analyze_cache(session, cache_min_tokens, cache_ttl, overrides))

    denom = usage.cache_read_tokens + usage.cache_creation_tokens + usage.input_tokens
    cache_hit_ratio = usage.cache_read_tokens / denom if denom else 0.0

    merged_rereads = _merge_rereads(rereads)
    sorted_oversized = sorted(oversized, key=lambda r: -r.estimated_tokens)
    sorted_cache_misses = sorted(cache_misses, key=lambda m: -m.extra_cost)

    suggestions = generate_suggestions(
        oversized=sorted_oversized,
        rereads=merged_rereads,
        cache_misses=sorted_cache_misses,
        overrides=overrides,
    )

    return Report(
        session_count=len(sessions),
        usage=usage,
        cost=cost,
        tool_spend=_merge_tool_spend(tool_spend),
        rereads=merged_rereads,
        oversized=sorted_oversized,
        cache_misses=sorted_cache_misses,
        cache_hit_ratio=cache_hit_ratio,
        suggestions=suggestions,
    )
