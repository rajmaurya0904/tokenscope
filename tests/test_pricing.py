import json
import tempfile
from pathlib import Path

from tokenscope.models import Usage
from tokenscope.pricing import (
    TokenCost,
    get_model_pricing,
    load_pricing_overrides,
    price_usage,
)


def test_known_model_pricing() -> None:
    """Test that known model pricing returns correct values."""
    pricing = get_model_pricing("claude-opus-4-1")
    assert pricing.input_per_million == 15.0
    assert pricing.output_per_million == 75.0
    assert pricing.cache_read_per_million == 1.5
    assert pricing.cache_write_per_million == 15.0
    assert pricing.estimated is False


def test_known_model_cost() -> None:
    """Test that known model cost matches hand-computed value."""
    # claude-sonnet-4: 3.0 input, 15.0 output, 0.3 cache_read, 3.0 cache_write (per million)
    usage = Usage(
        input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000
    )

    cost = price_usage(usage, "claude-sonnet-4")

    # Expected: 1M * 3.0 / 1M + 1M * 15.0 / 1M + 1M * 0.3 / 1M = 3.0 + 15.0 + 0.3 = 18.3
    assert cost.amount == 18.3
    assert cost.estimated is False


def test_unknown_model_uses_fallback() -> None:
    """Test that unknown model uses fallback pricing with estimated flag."""
    pricing = get_model_pricing("unknown-model-v99")
    assert pricing.input_per_million == 1.0
    assert pricing.output_per_million == 5.0
    assert pricing.cache_read_per_million == 0.1
    assert pricing.cache_write_per_million == 1.0
    assert pricing.estimated is True


def test_unknown_model_cost_is_estimated() -> None:
    """Test that cost for unknown model is marked as estimated."""
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = price_usage(usage, "unknown-model")

    # Expected: 1M * 1.0 / 1M + 1M * 5.0 / 1M = 1.0 + 5.0 = 6.0
    assert cost.amount == 6.0
    assert cost.estimated is True


def test_json_override_file_changes_result() -> None:
    """Test that JSON override file changes pricing results."""
    override_data = {
        "custom-model": {
            "input_per_million": 10.0,
            "output_per_million": 20.0,
            "cache_read_per_million": 1.0,
            "cache_write_per_million": 10.0,
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = Path(tmpdir) / "pricing_overrides.json"
        with open(json_file, "w") as f:
            json.dump(override_data, f)

        overrides = load_pricing_overrides(str(json_file))
        cost = price_usage(
            Usage(input_tokens=1_000_000, output_tokens=1_000_000),
            "custom-model",
            overrides,
        )

        # Expected: 1M * 10.0 / 1M + 1M * 20.0 / 1M = 10.0 + 20.0 = 30.0
        assert cost.amount == 30.0
        assert cost.estimated is False


def test_json_override_doesnt_affect_known_models() -> None:
    """Test that overrides only apply to specified models."""
    override_data = {
        "other-model": {
            "input_per_million": 100.0,
            "output_per_million": 100.0,
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = Path(tmpdir) / "pricing_overrides.json"
        with open(json_file, "w") as f:
            json.dump(override_data, f)

        overrides = load_pricing_overrides(str(json_file))
        cost = price_usage(
            Usage(input_tokens=1_000_000, output_tokens=1_000_000),
            "claude-opus-4-1",
            overrides,
        )

        # Should use known model pricing, not override
        # Expected: 1M * 15.0 / 1M + 1M * 75.0 / 1M = 15.0 + 75.0 = 90.0
        assert cost.amount == 90.0
        assert cost.estimated is False


def test_cache_tokens_pricing() -> None:
    """Test that cache read and write tokens are priced correctly."""
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
    )

    cost = price_usage(usage, "claude-haiku-3")

    # Expected: 1M * 0.025 / 1M + 1M * 0.25 / 1M = 0.025 + 0.25 = 0.275
    assert cost.amount == 0.275
    assert cost.estimated is False


def test_price_usage_returns_token_cost() -> None:
    """Test that price_usage returns TokenCost dataclass."""
    usage = Usage(input_tokens=100)
    cost = price_usage(usage, "gpt-4")

    assert isinstance(cost, TokenCost)
    assert cost.amount == 100 * 30.0 / 1_000_000
    assert cost.estimated is False


def test_empty_usage_zero_cost() -> None:
    """Test that empty usage results in zero cost."""
    usage = Usage()
    cost = price_usage(usage, "claude-opus-4-1")

    assert cost.amount == 0.0
    assert cost.estimated is False
