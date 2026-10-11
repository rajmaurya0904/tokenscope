"""Suggestion engine: map analyzer findings to concrete, actionable recommendations."""

from __future__ import annotations

from dataclasses import dataclass

from tcwa.analyzers.cache import CacheMiss
from tcwa.analyzers.oversized import OversizedResult
from tcwa.analyzers.rereads import FileReread
from tcwa.pricing import ModelPricing, get_model_pricing

# Assumed fraction of an oversized result's tokens that a filter/limit could trim.
_OVERSIZED_SAVINGS_FRACTION = 0.8


@dataclass
class Suggestion:
    """A concrete recommendation with an estimated savings."""

    category: str
    message: str
    estimated_tokens_saved: int
    estimated_dollars_saved: float


def _dollars_for_tokens(
    tokens: int, model: str = "", overrides: dict[str, ModelPricing] | None = None
) -> float:
    pricing = get_model_pricing(model, overrides)
    return tokens * pricing.input_per_million / 1_000_000


def suggest_for_oversized(
    results: list[OversizedResult],
    model: str = "",
    overrides: dict[str, ModelPricing] | None = None,
) -> list[Suggestion]:
    """Suggest trimming oversized tool outputs with a limit/offset or a filter."""
    suggestions = []
    for r in results:
        tokens_saved = int(r.estimated_tokens * _OVERSIZED_SAVINGS_FRACTION)
        if tokens_saved <= 0:
            continue
        if r.tool == "Read" and r.has_no_limit:
            message = f"Use Read with offset/limit for {r.command}"
        elif r.tool == "Bash":
            message = f"Add head/tail or grep filter to {r.command}"
        else:
            message = f"Trim the oversized output from {r.tool} on {r.command}"
        suggestions.append(
            Suggestion(
                category="oversized_output",
                message=message,
                estimated_tokens_saved=tokens_saved,
                estimated_dollars_saved=_dollars_for_tokens(tokens_saved, model, overrides),
            )
        )
    return suggestions


def suggest_for_rereads(
    results: list[FileReread],
    model: str = "",
    overrides: dict[str, ModelPricing] | None = None,
) -> list[Suggestion]:
    """Suggest noting frequently re-read files in CLAUDE.md so they aren't re-read."""
    suggestions = []
    for r in results:
        if r.wasted_tokens <= 0:
            continue
        suggestions.append(
            Suggestion(
                category="repeated_reread",
                message=f"Note file {r.path} in CLAUDE.md to avoid re-reads",
                estimated_tokens_saved=r.wasted_tokens,
                estimated_dollars_saved=_dollars_for_tokens(r.wasted_tokens, model, overrides),
            )
        )
    return suggestions


def suggest_for_cache(results: list[CacheMiss]) -> list[Suggestion]:
    """Suggest batching work to stay within the cache TTL and avoid cold cache writes."""
    suggestions = []
    for r in results:
        if r.extra_cost <= 0:
            continue
        suggestions.append(
            Suggestion(
                category="cache_miss",
                message="Batch work to stay within cache TTL",
                estimated_tokens_saved=r.cache_creation_tokens,
                estimated_dollars_saved=r.extra_cost,
            )
        )
    return suggestions


def generate_suggestions(
    oversized: list[OversizedResult] | None = None,
    rereads: list[FileReread] | None = None,
    cache_misses: list[CacheMiss] | None = None,
    model: str = "",
    overrides: dict[str, ModelPricing] | None = None,
) -> list[Suggestion]:
    """Combine suggestions from all finding types, sorted by descending savings."""
    suggestions: list[Suggestion] = []
    suggestions.extend(suggest_for_oversized(oversized or [], model, overrides))
    suggestions.extend(suggest_for_rereads(rereads or [], model, overrides))
    suggestions.extend(suggest_for_cache(cache_misses or []))
    return sorted(
        suggestions,
        key=lambda s: (-s.estimated_dollars_saved, -s.estimated_tokens_saved),
    )
