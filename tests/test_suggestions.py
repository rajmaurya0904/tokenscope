from tokenscope.analyzers.cache import CacheMiss
from tokenscope.analyzers.oversized import OversizedResult
from tokenscope.analyzers.rereads import FileReread
from tokenscope.suggestions import (
    generate_suggestions,
    suggest_for_cache,
    suggest_for_oversized,
    suggest_for_rereads,
)


def test_oversized_read_without_limit_suggests_offset_limit() -> None:
    finding = OversizedResult(
        tool="Read", command="big.log", estimated_tokens=10_000, has_no_limit=True
    )
    [s] = suggest_for_oversized([finding])
    assert s.category == "oversized_output"
    assert "offset/limit" in s.message
    assert "big.log" in s.message
    assert s.estimated_tokens_saved > 0
    assert s.estimated_dollars_saved > 0


def test_oversized_bash_suggests_filter() -> None:
    [s] = suggest_for_oversized(
        [OversizedResult(tool="Bash", command="npm test", estimated_tokens=8_000)]
    )
    assert "head/tail or grep filter" in s.message
    assert "npm test" in s.message
    assert s.estimated_tokens_saved > 0
    assert s.estimated_dollars_saved > 0


def test_rereads_suggest_claude_md_note() -> None:
    finding = FileReread(path="src/big.py", reads=3, wasted_reads=2, wasted_tokens=4_000)
    [s] = suggest_for_rereads([finding])
    assert s.category == "repeated_reread"
    assert "CLAUDE.md" in s.message
    assert "src/big.py" in s.message
    assert s.estimated_tokens_saved == 4_000
    assert s.estimated_dollars_saved > 0


def test_cache_miss_suggests_batching() -> None:
    finding = CacheMiss(
        turn_index=3,
        cache_creation_tokens=6_000,
        gap_seconds=900.0,
        prefix_changed=False,
        extra_cost=0.05,
    )
    [s] = suggest_for_cache([finding])
    assert s.category == "cache_miss"
    assert "cache TTL" in s.message
    assert s.estimated_tokens_saved == 6_000
    assert s.estimated_dollars_saved == 0.05


def test_zero_savings_findings_produce_no_suggestion() -> None:
    empty_read = OversizedResult(tool="Read", command="x", estimated_tokens=0)
    assert suggest_for_oversized([empty_read]) == []
    empty_reread = FileReread(path="x", reads=1, wasted_reads=0, wasted_tokens=0)
    assert suggest_for_rereads([empty_reread]) == []
    empty_miss = CacheMiss(
        turn_index=0, cache_creation_tokens=0, gap_seconds=None, prefix_changed=True, extra_cost=0.0
    )
    assert suggest_for_cache([empty_miss]) == []


def test_generate_suggestions_covers_each_type_and_sorts_by_descending_savings() -> None:
    oversized = [OversizedResult(tool="Bash", command="npm test", estimated_tokens=1_000)]
    rereads = [FileReread(path="a.py", reads=2, wasted_reads=1, wasted_tokens=50_000)]
    cache_misses = [
        CacheMiss(
            turn_index=1,
            cache_creation_tokens=2_000,
            gap_seconds=600.0,
            prefix_changed=False,
            extra_cost=0.01,
        )
    ]

    suggestions = generate_suggestions(
        oversized=oversized, rereads=rereads, cache_misses=cache_misses
    )

    assert len(suggestions) == 3
    categories = {s.category for s in suggestions}
    assert categories == {"oversized_output", "repeated_reread", "cache_miss"}

    savings = [s.estimated_dollars_saved for s in suggestions]
    assert savings == sorted(savings, reverse=True)
    # The big re-read (50k tokens) should dominate the small oversized Bash output (1k tokens).
    assert suggestions[0].category == "repeated_reread"


def test_generate_suggestions_handles_no_findings() -> None:
    assert generate_suggestions() == []
