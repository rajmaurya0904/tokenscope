from datetime import datetime, timedelta

import pytest

from tokenscope.analyzers.cache import analyze_cache, cache_hit_ratio
from tokenscope.models import Session, Turn, Usage

BASE = datetime(2024, 1, 1, 12, 0, 0)


def _turn(index: int, minute_offset: float, usage: Usage, model: str = "claude-sonnet-4") -> Turn:
    return Turn(
        index=index,
        model=model,
        timestamp=BASE + timedelta(minutes=minute_offset),
        usage=usage,
    )


def _session(*turns: Turn) -> Session:
    return Session(id="s", provider="claude", turns=list(turns))


def test_cache_hit_ratio_matches_hand_computed_value() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_creation_tokens=500)),
        _turn(1, 1, Usage(input_tokens=50, cache_read_tokens=900)),
    )
    # input=150, cache_read=900, cache_creation=500 -> denom=1550
    assert cache_hit_ratio(session) == pytest.approx(900 / 1550)


def test_cache_hit_ratio_zero_when_no_relevant_tokens() -> None:
    assert cache_hit_ratio(_session(Turn(index=0))) == 0.0


def test_gap_over_ttl_with_large_cache_creation_is_flagged() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_read_tokens=900)),
        _turn(1, 10, Usage(input_tokens=100, cache_creation_tokens=5000)),  # 10 min later
    )
    [miss] = analyze_cache(session)
    assert miss.turn_index == 1
    assert miss.gap_seconds == pytest.approx(600.0)
    assert miss.extra_cost > 0


def test_fully_warm_session_yields_no_flags() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_read_tokens=900)),
        _turn(1, 1, Usage(input_tokens=100, cache_creation_tokens=5000)),  # 1 min later
        _turn(2, 2, Usage(input_tokens=100, cache_read_tokens=5900)),
    )
    assert analyze_cache(session) == []


def test_small_cache_creation_not_flagged_despite_gap() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_read_tokens=900)),
        _turn(1, 10, Usage(input_tokens=100, cache_creation_tokens=10)),
    )
    assert analyze_cache(session, min_cache_creation_tokens=1000) == []


def test_model_change_flags_as_prefix_change_even_within_ttl() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_read_tokens=900), model="claude-sonnet-4"),
        _turn(1, 1, Usage(input_tokens=100, cache_creation_tokens=5000), model="claude-opus-4-1"),
    )
    [miss] = analyze_cache(session)
    assert miss.prefix_changed is True
    assert miss.gap_seconds == pytest.approx(60.0)


def test_first_turn_never_flagged() -> None:
    session = _session(
        _turn(0, 0, Usage(input_tokens=100, cache_creation_tokens=5000)),
    )
    assert analyze_cache(session) == []


def test_missing_timestamp_relies_on_prefix_change_only() -> None:
    session = _session(
        Turn(
            index=0,
            model="claude-sonnet-4",
            usage=Usage(input_tokens=100, cache_read_tokens=900),
        ),
        Turn(
            index=1,
            model="claude-sonnet-4",
            usage=Usage(input_tokens=100, cache_creation_tokens=5000),
        ),
    )
    assert analyze_cache(session) == []
