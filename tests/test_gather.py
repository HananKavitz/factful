from __future__ import annotations

import pytest
from pydantic import BaseModel

from factful.agents.fetch import Page
from factful.agents.gather import (
    build_expand_prompt,
    build_mine_prompt,
    dedupe_by_url,
    find_passage_para,
    gather,
)
from factful.agents.search import SearchResult
from factful.config import Settings
from factful.schemas import ClaimMineOutput, MinedClaim, QueryExpansion, SourceBundle

TOPIC = "global semiconductor market"
ANGLE = "geopolitical supply chains"

SEARCH_RESULTS = [
    SearchResult(url="https://reports.example/market", title="Market Report"),
    SearchResult(url="https://reports.example/market", title="Market Report dup"),
    SearchResult(url="https://www.analytics.example/data", title="Analytics Data"),
    SearchResult(url="https://news.example/failed", title="404 page"),
]

PAGES = {
    "https://reports.example/market": Page(
        url="https://reports.example/market",
        title="Market Report",
        publish_date="2024-01-01",
        text="The market grew.\nRevenue hit $4B in 2024.",
    ),
    "https://www.analytics.example/data": Page(
        url="https://www.analytics.example/data",
        title="Analytics Data",
        publish_date="2024-02-01",
        text="Analysts expect 9% growth and 2.1 million jobs.",
    ),
}

MINED = ClaimMineOutput(
    claims=[
        MinedClaim(
            claim="Revenue hit $4B in 2024",
            key_stat="$4B",
            quote_snippet="Revenue hit $4B in 2024.",
        ),
        MinedClaim(
            claim="Chinese suppliers grew by 27%",
            key_stat="27%",
            quote_snippet="China rose 27%.",
        ),
    ]
)


class FakeClient:
    def __init__(self, expansion: QueryExpansion, mine: ClaimMineOutput) -> None:
        self.expansion = expansion
        self.mine = mine
        self.calls: list[tuple[str, type[BaseModel]]] = []

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((prompt, schema))
        if schema is QueryExpansion:
            return self.expansion
        if schema is ClaimMineOutput:
            return self.mine
        raise AssertionError(f"unexpected schema {schema}")


class FakeSearcher:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str) -> list[SearchResult]:
        self.queries.append(query)
        return self.results


class FakeFetcher:
    def __init__(self, pages: dict[str, Page]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> Page | None:
        return self.pages.get(url)


def run_gather() -> tuple[SourceBundle, FakeClient, FakeSearcher]:
    client = FakeClient(
        expansion=QueryExpansion(
            queries=["market size", "growth figures", "top suppliers", "supply chain exposure"]
        ),
        mine=MINED,
    )
    searcher = FakeSearcher(SEARCH_RESULTS)
    fetcher = FakeFetcher(PAGES)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=searcher,
        fetcher=fetcher,
    )
    return bundle, client, searcher


def test_expand_queries_prompt_reflects_topic_and_angle() -> None:
    prompt = build_expand_prompt(TOPIC, ANGLE)
    assert TOPIC in prompt
    assert ANGLE in prompt
    assert "between 4 and 6" in prompt


def test_mine_prompt_injects_page_text() -> None:
    page = PAGES["https://reports.example/market"]
    prompt = build_mine_prompt(page)
    assert "Revenue hit $4B in 2024." in prompt
    assert "verbatim" in prompt.lower()


def test_dedupe_by_url_keeps_first_and_filters_duplicates() -> None:
    out = dedupe_by_url(SEARCH_RESULTS)
    assert len(out) == 3
    assert out[0].url == "https://reports.example/market"
    assert "analytics.example" in out[1].url


def test_dedupe_by_url_ignores_trailing_slash_and_fragment() -> None:
    results = [
        SearchResult(url="https://x.example/a", title="a"),
        SearchResult(url="https://x.example/a#section", title="b"),
        SearchResult(url="https://x.example/a/", title="c"),
    ]
    out = dedupe_by_url(results)
    assert len(out) == 1


def test_dedupe_by_url_folds_scheme_and_www() -> None:
    results = [
        SearchResult(url="https://www.example.com/report", title="a"),
        SearchResult(url="http://example.com/report", title="b"),
        SearchResult(url="https://EXAMPLE.com/report", title="c"),
    ]
    out = dedupe_by_url(results)
    assert len(out) == 1


def test_find_passage_para_looks_up_quote() -> None:
    text = "Opening line.\nThe core figure: Revenue hit $4B in 2024."
    assert find_passage_para(text, "Revenue hit $4B in 2024.") == "para-2"


def test_find_passage_para_missing_quote_is_para_0() -> None:
    assert find_passage_para("No numbers here.", "nonexistent quote") == "para-0"


def test_gather_produces_source_bundle() -> None:
    bundle, client, searcher = run_gather()
    assert isinstance(bundle, SourceBundle)
    assert bundle.topic == TOPIC
    assert bundle.angle == ANGLE
    assert [c.claim_id for c in bundle.citations] == ["c1", "c2", "c3", "c4"]


def test_gather_wires_citation_fields() -> None:
    bundle, _, _ = run_gather()
    first = bundle.citations[0]
    assert first.claim == "Revenue hit $4B in 2024"
    assert first.source_url == "https://reports.example/market"
    assert first.key_stat == "$4B"
    assert first.quote_snippet == "Revenue hit $4B in 2024."
    assert first.passage_ref == "para-2"
    assert first.publisher == "reports.example"
    assert first.publish_date == "2024-01-01"
    assert first.retrieved_at.tzinfo is not None


def test_gather_skips_unfetchable_pages() -> None:
    bundle, _, _ = run_gather()
    urls = {c.source_url for c in bundle.citations}
    assert "https://news.example/failed" not in urls


def test_gather_searches_each_expanded_query() -> None:
    _, _, searcher = run_gather()
    assert searcher.queries == [
        "market size",
        "growth figures",
        "top suppliers",
        "supply chain exposure",
    ]


def test_gather_deduplicates_expanded_queries() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["size", "size", "growth", "jobs"]),
        mine=MINED,
    )
    searcher = FakeSearcher(SEARCH_RESULTS)
    gather(TOPIC, ANGLE, client=client, searcher=searcher, fetcher=FakeFetcher(PAGES))
    assert searcher.queries == ["size", "growth", "jobs"]


def test_gather_honors_max_sources_from_settings() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=FakeFetcher(PAGES),
        settings=Settings.model_validate({"gather": {"max_sources": 1}}),
    )
    assert {c.source_url for c in bundle.citations} == {"https://reports.example/market"}


def test_gather_raises_when_no_pages_fetchable() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    with pytest.raises(ValueError, match="no citations"):
        gather(
            TOPIC,
            ANGLE,
            client=client,
            searcher=FakeSearcher(SEARCH_RESULTS),
            fetcher=FakeFetcher({}),
        )


def test_gather_skips_empty_text_page() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    empty = Page(
        url="https://reports.example/market",
        title="Empty",
        publish_date="",
        text="",
    )
    fetcher = FakeFetcher({"https://reports.example/market": empty})
    with pytest.raises(ValueError, match="no citations"):
        gather(
            TOPIC,
            ANGLE,
            client=client,
            searcher=FakeSearcher([SearchResult(url="https://reports.example/market", title="E")]),
            fetcher=fetcher,
        )
