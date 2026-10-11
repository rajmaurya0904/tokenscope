"""Cache hit ratio and cache-miss (cold cache-write) detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from tcwa.models import Session, Turn
from tcwa.pricing import ModelPricing, get_model_pricing

DEFAULT_TTL = timedelta(minutes=5)


@dataclass
class CacheMiss:
    """A turn whose large cache_creation likely paid full cache-write price."""

    turn_index: int
    cache_creation_tokens: int
    gap_seconds: float | None
    prefix_changed: bool
    extra_cost: float


def cache_hit_ratio(session: Session) -> float:
    """cache_read / (cache_read + cache_creation + input), aggregated over the session.

    Returns 0.0 for a session with no relevant tokens, to avoid a division by zero.
    """
    usage = session.usage
    denom = usage.cache_read_tokens + usage.cache_creation_tokens + usage.input_tokens
    if denom == 0:
        return 0.0
    return usage.cache_read_tokens / denom


def analyze_cache(
    session: Session,
    min_cache_creation_tokens: int = 1000,
    ttl: timedelta = DEFAULT_TTL,
    overrides: dict[str, ModelPricing] | None = None,
) -> list[CacheMiss]:
    """Flag turns with a large cache_creation following an idle gap or a prefix change.

    A prefix change is approximated by a model switch between consecutive turns,
    since either invalidates the previously cached prefix. The session's first
    turn with usage is never flagged, as there is nothing prior for it to have
    reused from cache.
    """
    misses: list[CacheMiss] = []
    prev: Turn | None = None
    for turn in session.turns:
        if turn.usage.total_tokens == 0:
            continue
        if prev is not None and turn.usage.cache_creation_tokens >= min_cache_creation_tokens:
            gap: float | None = None
            if turn.timestamp is not None and prev.timestamp is not None:
                gap = (turn.timestamp - prev.timestamp).total_seconds()
            prefix_changed = turn.model != prev.model
            if prefix_changed or (gap is not None and gap > ttl.total_seconds()):
                pricing = get_model_pricing(turn.model or "", overrides)
                extra_cost = (
                    turn.usage.cache_creation_tokens
                    * (pricing.cache_write_per_million - pricing.cache_read_per_million)
                    / 1_000_000
                )
                misses.append(
                    CacheMiss(
                        turn_index=turn.index,
                        cache_creation_tokens=turn.usage.cache_creation_tokens,
                        gap_seconds=gap,
                        prefix_changed=prefix_changed,
                        extra_cost=extra_cost,
                    )
                )
        prev = turn
    return misses
