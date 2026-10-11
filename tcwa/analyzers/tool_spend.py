"""Per-tool token spend: tool_result size plus its re-billing as carried context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tcwa.models import Session
from tcwa.pricing import ModelPricing, get_model_pricing

Tokenizer = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    """Default tokenizer: the chars/4 heuristic (rounded up)."""
    return -(-len(text) // 4)


@dataclass
class ToolSpend:
    """Aggregated spend attributed to one tool."""

    tool: str
    calls: int = 0
    output_tokens: int = 0
    carried_tokens: int = 0
    cost: float = 0.0


def analyze_tool_spend(
    session: Session,
    tokenizer: Tokenizer = estimate_tokens,
    overrides: dict[str, ModelPricing] | None = None,
) -> list[ToolSpend]:
    """Attribute tokens and dollars to each tool, sorted by descending cost.

    A result is billed once as input on the turn that made the call, then
    re-billed at the cache-read rate on every later turn (its carried context),
    each at that turn's model pricing.
    """
    turns = session.turns
    stats: dict[str, ToolSpend] = {}
    for pos, turn in enumerate(turns):
        names = {call.id: call.name for call in turn.tool_calls}
        for call in turn.tool_calls:
            stats.setdefault(call.name, ToolSpend(call.name)).calls += 1
        for result in turn.tool_results:
            name = names.get(result.tool_call_id)
            if name is None:
                continue
            tokens = tokenizer(result.content)
            spend = stats.setdefault(name, ToolSpend(name))
            later = turns[pos + 1 :]
            spend.output_tokens += tokens
            spend.carried_tokens += tokens * len(later)
            first = get_model_pricing(turn.model or "", overrides)
            spend.cost += tokens * first.input_per_million / 1_000_000
            for t in later:
                p = get_model_pricing(t.model or "", overrides)
                spend.cost += tokens * p.cache_read_per_million / 1_000_000
    return sorted(stats.values(), key=lambda s: (-s.cost, s.tool))
