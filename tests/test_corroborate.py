from datetime import UTC, datetime

from factful.schemas import Citation
from factful.verify.corroborate import (
    contradicting_sources,
    corroborating_sources,
    extract_numbers,
    normalize_key_stat,
)


def make_citation(
    claim_id: str,
    key_stat: str,
    source_url: str = "https://example.com/source",
) -> Citation:
    return Citation(
        claim_id=claim_id,
        claim=f"claim {claim_id}",
        source_url=source_url,
        source_title="Source",
        publisher="example.com",
        publish_date="2024-01-01",
        key_stat=key_stat,
        quote_snippet=f"supports {key_stat}",
        passage_ref="para-1",
        retrieved_at=datetime(2024, 1, 2, tzinfo=UTC),
    )


UREA = "https://example.com/report-a"
UREB = "https://example.com/report-b"
UREC = "https://example.com/report-c"


def test_extract_numbers_plain() -> None:
    assert extract_numbers("4.2% and 12") == [4.2, 12.0]


def test_extract_numbers_thousands_separator() -> None:
    assert extract_numbers("3,000 jobs") == [3000.0]


def test_normalize_key_stat() -> None:
    assert normalize_key_stat("$4B") == (4.0, "billion")
    assert normalize_key_stat("12%") == (12.0, "%")


def test_normalize_key_stat_canonicalizes_spellings() -> None:
    assert normalize_key_stat("$4 billion") == (4.0, "billion")
    assert normalize_key_stat("12 percent") == (12.0, "%")
    assert normalize_key_stat("3,000") == (3000.0, "")


def test_normalize_key_stat_none_when_no_number() -> None:
    assert normalize_key_stat("huge growth") is None


def test_corroborating_sources_matching_stat() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "27%", UREB),
        make_citation("c3", "$4B", UREC),
    ]
    assert corroborating_sources(citations, citations[0]) == [UREC]


def test_corroborating_sources_self_excluded() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "$4B", UREB),
    ]
    assert corroborating_sources(citations, citations[1]) == [UREA]


def test_corroborating_sources_ignores_other_units() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "4 people", UREB),
    ]
    assert corroborating_sources(citations, citations[0]) == []


def test_corroborating_sources_require_independent_urls() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "$4B", UREA),
    ]
    assert corroborating_sources(citations, citations[0]) == []


def test_corroborating_sources_dedupe_same_url() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "$4B", UREA),
        make_citation("c3", "$4B", UREB),
    ]
    assert corroborating_sources(citations, citations[0]) == [UREB]


def test_contradicting_sources_denote_disagreement() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "$5B", UREB),
    ]
    assert contradicting_sources(citations, citations[0]) == [UREB]


def test_contradicting_sources_ignore_different_units() -> None:
    citations = [
        make_citation("c1", "$4B", UREA),
        make_citation("c2", "27%", UREB),
    ]
    assert contradicting_sources(citations, citations[0]) == []
