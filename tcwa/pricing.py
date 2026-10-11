"""Token cost model with per-model pricing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tcwa.models import Usage


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing for a model."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: float
    cache_write_per_million: float
    estimated: bool = False


@dataclass(frozen=True)
class TokenCost:
    """Calculated cost for a usage."""

    amount: float
    estimated: bool


# Known model pricing (per million tokens)
_KNOWN_MODELS = {
    "claude-opus-4-1": ModelPricing(
        input_per_million=15.0,
        output_per_million=75.0,
        cache_read_per_million=1.5,
        cache_write_per_million=15.0,
    ),
    "claude-sonnet-4": ModelPricing(
        input_per_million=3.0,
        output_per_million=15.0,
        cache_read_per_million=0.3,
        cache_write_per_million=3.0,
    ),
    "claude-haiku-3": ModelPricing(
        input_per_million=0.25,
        output_per_million=1.25,
        cache_read_per_million=0.025,
        cache_write_per_million=0.25,
    ),
    "gpt-4": ModelPricing(
        input_per_million=30.0,
        output_per_million=60.0,
        cache_read_per_million=15.0,
        cache_write_per_million=30.0,
    ),
    "gpt-3.5-turbo": ModelPricing(
        input_per_million=0.5,
        output_per_million=1.5,
        cache_read_per_million=0.25,
        cache_write_per_million=0.5,
    ),
}

# Fallback pricing for unknown models (marked as estimated)
_FALLBACK_PRICING = ModelPricing(
    input_per_million=1.0,
    output_per_million=5.0,
    cache_read_per_million=0.1,
    cache_write_per_million=1.0,
    estimated=True,
)


def get_model_pricing(
    model: str, overrides: dict[str, ModelPricing] | None = None
) -> ModelPricing:
    """Get pricing for a model with optional overrides."""
    if overrides and model in overrides:
        return overrides[model]
    if model in _KNOWN_MODELS:
        return _KNOWN_MODELS[model]
    return _FALLBACK_PRICING


def load_pricing_overrides(json_file: str) -> dict[str, ModelPricing]:
    """Load pricing overrides from a JSON file."""
    path = Path(json_file)
    if not path.exists():
        return {}

    with open(path) as f:
        data = json.load(f)

    overrides = {}
    for model, prices in data.items():
        overrides[model] = ModelPricing(
            input_per_million=prices["input_per_million"],
            output_per_million=prices["output_per_million"],
            cache_read_per_million=prices.get("cache_read_per_million", 0),
            cache_write_per_million=prices.get("cache_write_per_million", 0),
            estimated=prices.get("estimated", False),
        )
    return overrides


def price_usage(
    usage: Usage, model: str, overrides: dict[str, ModelPricing] | None = None
) -> TokenCost:
    """Calculate the cost for a usage on a given model."""
    pricing = get_model_pricing(model, overrides)

    cost = (
        usage.input_tokens * pricing.input_per_million / 1_000_000
        + usage.output_tokens * pricing.output_per_million / 1_000_000
        + usage.cache_read_tokens * pricing.cache_read_per_million / 1_000_000
        + usage.cache_creation_tokens * pricing.cache_write_per_million / 1_000_000
    )

    return TokenCost(amount=cost, estimated=pricing.estimated)
