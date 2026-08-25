import pytest

from mini_research.models import SearchResult
from mini_research.tools.search import canonicalize_url, register_search_results


def test_canonicalize_removes_tracking_fragment_and_trailing_slash() -> None:
    left = canonicalize_url("https://Example.com/paper/?utm_source=x&id=1#results")
    right = canonicalize_url("https://example.com/paper?id=1")
    assert left == right


def test_canonicalize_rejects_non_web_scheme() -> None:
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        canonicalize_url("ftp://example.com/file")


def test_register_sources_deduplicates_across_rounds_and_keeps_id() -> None:
    first = SearchResult(
        query="first query",
        title="Paper",
        url="https://example.com/paper?utm_source=test",
        content="short",
        score=0.5,
    )
    sources, new_ids = register_search_results({}, [first], max_new_sources=3)
    assert new_ids == ["S1"]

    duplicate = SearchResult(
        query="second query",
        title="Paper duplicate",
        url="https://example.com/paper#section",
        content="a longer copy of the same page",
        score=0.9,
    )
    sources, new_ids = register_search_results(sources, [duplicate], max_new_sources=3)
    assert new_ids == []
    assert list(sources) == ["S1"]
    assert sources["S1"].discovered_by == ["first query", "second query"]
    assert sources["S1"].search_score == 0.9
