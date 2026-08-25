from mini_research.citations import extract_citation_ids, render_report, validate_citations
from mini_research.models import SourceRecord


def make_source(source_id: str, url: str) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        url=url,
        canonical_url=url,
        title=f"Title {source_id}",
        domain="example.com",
    )


def test_extracts_unique_citations_in_appearance_order() -> None:
    assert extract_citation_ids("A [S2], B [S1], C [S2]") == ["S2", "S1"]


def test_accepts_padding_around_a_valid_source_id() -> None:
    sources = {
        "S1": make_source("S1", "https://example.com/one"),
        "S2": make_source("S2", "https://example.com/two"),
    }

    result = validate_citations("Claim [ S1 ][\tS2\t].", sources)

    assert result.valid
    assert result.referenced_ids == ["S1", "S2"]


def test_padding_is_removed_when_rendering_citation_links() -> None:
    sources = {"S1": make_source("S1", "https://example.com/one")}

    report = render_report("A supported claim [ S1 ].", sources)

    assert "[S1](https://example.com/one)" in report
    assert "[ S1 ]" not in report


def test_padded_unknown_id_is_still_rejected() -> None:
    sources = {"S1": make_source("S1", "https://example.com/one")}

    result = validate_citations("Unsupported claim [ S999 ].", sources)

    assert not result.valid
    assert result.unknown_ids == ["S999"]


def test_does_not_accept_grouped_source_ids() -> None:
    sources = {
        "S1": make_source("S1", "https://example.com/one"),
        "S2": make_source("S2", "https://example.com/two"),
    }

    result = validate_citations("Claim [S1, S2].", sources)

    assert not result.valid
    assert result.referenced_ids == []


def test_rejects_unknown_ids_and_bare_urls() -> None:
    sources = {"S1": make_source("S1", "https://example.com/one")}
    result = validate_citations("Claim [S999] https://invented.example", sources)
    assert not result.valid
    assert result.unknown_ids == ["S999"]
    assert result.bare_urls == ["https://invented.example"]


def test_renders_only_registered_referenced_sources() -> None:
    sources = {
        "S1": make_source("S1", "https://example.com/one"),
        "S2": make_source("S2", "https://example.com/two"),
    }
    report = render_report("A supported claim [S2].", sources)
    assert "[S2](https://example.com/two)" in report
    assert "Title S2" in report
    assert "Title S1" not in report
