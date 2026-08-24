from __future__ import annotations

import re
from datetime import date

import pytest
from pydantic import BaseModel

from factful.agents.fetch import Page
from factful.agents.gather import (
    MAX_MINE_TEXT_CHARACTERS,
    build_expand_prompt,
    build_mine_prompt,
    build_relevance_prompt,
    dedupe_by_url,
    filter_relevant,
    find_passage_para,
    gather,
    truncate_text,
)
from factful.agents.search import SearchResult
from factful.config import Settings
from factful.schemas import (
    ClaimMineOutput,
    MinedClaim,
    QueryExpansion,
    RelevanceSelection,
    SourceBundle,
)

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
    def __init__(
        self,
        expansion: QueryExpansion,
        mine: ClaimMineOutput,
        selection: RelevanceSelection | None = None,
    ) -> None:
        self.expansion = expansion
        self.mine = mine
        self.selection = selection
        self.calls: list[tuple[str, type[BaseModel]]] = []

    def _prompt_claim_ids(self, prompt: str) -> list[str]:
        return re.findall(r"claim_id=(\w+)", prompt)

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((prompt, schema))
        if schema is QueryExpansion:
            return self.expansion
        if schema is ClaimMineOutput:
            return self.mine
        if schema is RelevanceSelection:
            if self.selection is not None:
                return self.selection
            return RelevanceSelection(keep_claim_ids=self._prompt_claim_ids(prompt))
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


def test_expand_prompt_injects_today_date() -> None:
    prompt = build_expand_prompt(TOPIC, ANGLE, today=date(2026, 8, 13))
    assert "Today is 2026-08-13" in prompt


def test_expand_prompt_defaults_to_current_date() -> None:
    prompt = build_expand_prompt(TOPIC, ANGLE)
    assert f"Today is {date.today().isoformat()}" in prompt


def test_expand_prompt_biases_queries_toward_recent_sources() -> None:
    prompt = build_expand_prompt(TOPIC, ANGLE, today=date(2026, 8, 13))
    assert "recent" in prompt.lower()


def test_mine_prompt_injects_page_text() -> None:
    page = PAGES["https://reports.example/market"]
    prompt = build_mine_prompt(page)
    assert "Revenue hit $4B in 2024." in prompt
    assert "verbatim" in prompt.lower()


def test_mine_prompt_truncates_oversized_page_text() -> None:
    page = Page(
        url="https://reports.example/market",
        title="Market Report",
        publish_date="2024-01-01",
        text="Revenue hit $4B in 2024.\n" * 50_000,
    )
    prompt = build_mine_prompt(page)
    assert len(page.text) > MAX_MINE_TEXT_CHARACTERS
    assert len(prompt) < len(page.text)
    assert "Revenue hit $4B in 2024." in prompt


def test_truncate_text_returns_short_text_unchanged() -> None:
    assert truncate_text("short text", max_characters=100) == "short text"


def test_truncate_text_cuts_at_sentence_boundary() -> None:
    text = "First sentence. Second sentence. Third sentence."
    assert truncate_text(text, max_characters=20) == "First sentence."


def test_truncate_text_falls_back_to_hard_cut() -> None:
    out = truncate_text("abcdefghijklmnopqrstuvwxyz", max_characters=10)
    assert out == "abcdefghij"


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


def test_gather_forwards_today_to_expansion_prompt() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=FakeFetcher(PAGES),
        today=date(2026, 8, 13),
    )
    assert "Today is 2026-08-13" in client.calls[0][0]


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


def test_relevance_prompt_reflects_topic_angle_and_claims() -> None:
    bundle, _, _ = run_gather()
    prompt = build_relevance_prompt(TOPIC, ANGLE, bundle.citations)
    assert TOPIC in prompt
    assert ANGLE in prompt
    assert "claim_id=c1" in prompt
    assert "Revenue hit $4B in 2024" in prompt
    assert "Chinese suppliers grew by 27%" in prompt


def test_relevance_prompt_injects_today_date() -> None:
    bundle, _, _ = run_gather()
    prompt = build_relevance_prompt(TOPIC, ANGLE, bundle.citations, today=date(2026, 8, 13))
    assert "Today is 2026-08-13" in prompt


def test_relevance_prompt_lists_each_candidate_once_with_metadata() -> None:
    bundle, _, _ = run_gather()
    prompt = build_relevance_prompt(TOPIC, ANGLE, bundle.citations)
    assert prompt.count("claim_id=") == 4
    assert "key_stat=$4B" in prompt
    assert "publisher=reports.example" in prompt


def test_filter_relevant_keeps_only_selected_claim_ids() -> None:
    bundle, _, _ = run_gather()
    relevance = RelevanceSelection(keep_claim_ids=["c2", "c4"])
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
        selection=relevance,
    )
    kept = filter_relevant(bundle.citations, TOPIC, ANGLE, client=client)
    assert [c.claim_id for c in kept] == ["c2", "c4"]


def test_filter_relevant_preserves_original_claim_order() -> None:
    bundle, _, _ = run_gather()
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
        selection=RelevanceSelection(keep_claim_ids=["c4", "c1"]),
    )
    kept = filter_relevant(bundle.citations, TOPIC, ANGLE, client=client)
    assert [c.claim_id for c in kept] == ["c1", "c4"]


def test_filter_relevant_returns_empty_input_without_calling_llm() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
        selection=RelevanceSelection(keep_claim_ids=["c1"]),
    )
    assert filter_relevant([], TOPIC, ANGLE, client=client) == []
    assert client.calls == []


def test_gather_drops_claims_rejected_by_relevance_filter() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
        selection=RelevanceSelection(keep_claim_ids=["c2", "c4"]),
    )
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=FakeFetcher(PAGES),
    )
    assert [c.claim_id for c in bundle.citations] == ["c2", "c4"]
    assert bundle.citations[0].claim == "Chinese suppliers grew by 27%"


def test_gather_falls_back_to_unfiltered_claims_when_relevance_filter_keeps_nothing() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
        selection=RelevanceSelection(keep_claim_ids=[]),
    )
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=FakeFetcher(PAGES),
    )
    assert [c.claim_id for c in bundle.citations] == ["c1", "c2", "c3", "c4"]


# ---- user_urls ---------------------------------------------------------------

USER_URL_PAGES = {
    "https://www.user-source.example/article": Page(
        url="https://www.user-source.example/article",
        title="User Article",
        publish_date="2025-03-01",
        text="The company raised $10M in Series A. The product has 50k users.",
    ),
}


def test_gather_with_user_urls_produces_citations() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    fetcher = FakeFetcher(PAGES | USER_URL_PAGES)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://www.user-source.example/article"],
    )
    user_citations = [c for c in bundle.citations if "user-source.example" in c.source_url]
    assert user_citations
    assert all(c.source_url == "https://www.user-source.example/article" for c in user_citations)
    # The fake client always returns MINED claims regardless of page text,
    # so user citations carry the same mined claims as search results.
    assert any("$4B" in c.claim for c in user_citations)
    assert any(c.publisher == "user-source.example" for c in user_citations)


def test_gather_user_urls_appear_before_search_results() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    fetcher = FakeFetcher(PAGES | USER_URL_PAGES)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://www.user-source.example/article"],
    )
    # First citations come from the user-provided URL
    assert bundle.citations[0].source_url == "https://www.user-source.example/article"
    assert bundle.citations[1].source_url == "https://www.user-source.example/article"


def test_gather_user_urls_skip_unfetchable() -> None:
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
        user_urls=["https://nonexistent.example/missing"],
    )
    urls = {c.source_url for c in bundle.citations}
    assert "https://nonexistent.example/missing" not in urls
    assert "https://reports.example/market" in urls


def test_gather_user_urls_dedup_with_search() -> None:
    """A URL supplied both by the user and by search results appears once."""
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    fetcher = FakeFetcher(PAGES)
    # "https://reports.example/market" is in both SEARCH_RESULTS and user_urls
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://reports.example/market"],
    )
    reports = [c for c in bundle.citations if "reports.example" in c.source_url]
    assert len(reports) == 2  # two mined claims from that page, not duplicated


def test_gather_user_urls_www_normalized_dedup() -> None:
    """www.reports.example/market is deduped against reports.example/market from search."""
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    www_page = Page(
        url="https://www.reports.example/market",
        title="Market Report",
        publish_date="2024-01-01",
        text="The market grew. Revenue hit $4B in 2024.",
    )
    fetcher = FakeFetcher(PAGES | {"https://www.reports.example/market": www_page})
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://www.reports.example/market"],
    )
    # User URL www.reports.example/market normalizes to reports.example/market,
    # which matches the search result.  Only 2 citations (the 2 MINED claims)
    # come from that page — no duplicate from the search loop.
    reports = [c for c in bundle.citations if "reports.example" in c.source_url]
    assert len(reports) == 2
    assert all(c.source_url == "https://www.reports.example/market" for c in reports)


def test_gather_no_user_urls_is_noop() -> None:
    """Passing user_urls=None or empty list leaves existing behaviour unchanged."""
    for user_urls in (None, []):
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
            user_urls=user_urls,
        )
        assert [c.claim_id for c in bundle.citations] == ["c1", "c2", "c3", "c4"]


def test_gather_honors_max_sources_with_user_urls() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    fetcher = FakeFetcher(PAGES | USER_URL_PAGES)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        settings=Settings.model_validate({"gather": {"max_sources": 1}}),
        user_urls=["https://www.user-source.example/article"],
    )
    assert len(bundle.citations) == 2  # pre-fetched user URL claims fill the slot


def test_gather_does_not_starve_search_when_user_url_yields_many_claims() -> None:
    """A user-supplied article with many mined claims does NOT consume the
    entire source budget.  The remaining budget is computed from unique source
    URLs, not from individual claims, so web search results still get fetched."""
    many_claims = ClaimMineOutput(
        claims=[
            MinedClaim(claim=f"Stat number {i}", key_stat=f"stat-{i}", quote_snippet="v." * i)
            for i in range(1, 10)
        ]
    )
    user_page = {
        "https://www.rich-source.example/long": Page(
            url="https://www.rich-source.example/long",
            title="Rich source",
            publish_date="2026-01-01",
            text=" ".join(f"Stat number {i}." for i in range(1, 10)),
        )
    }
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=many_claims,
    )
    fetcher = FakeFetcher(PAGES | user_page)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://www.rich-source.example/long"],
    )
    # User URL: 1 unique URL → consumes 1 source slot
    # Default limit is 10 → remaining = 9 search slots → at least one search
    # result gets fetched and mined.
    user_urls = {c.source_url for c in bundle.citations}
    search_urls = {
        c.source_url
        for c in bundle.citations
        if c.source_url != "https://www.rich-source.example/long"
    }
    assert len(user_urls) >= 2, (
        f"expected citations from ≥2 unique URLs, got {len(user_urls)}: user-only={user_urls}"
    )
    assert search_urls, "expected at least one search-result citation alongside user-URL citations"


def test_gather_stores_user_source_pages_in_bundle() -> None:
    client = FakeClient(
        expansion=QueryExpansion(queries=["q1", "q2", "q3", "q4"]),
        mine=MINED,
    )
    fetcher = FakeFetcher(PAGES | USER_URL_PAGES)
    bundle = gather(
        TOPIC,
        ANGLE,
        client=client,
        searcher=FakeSearcher(SEARCH_RESULTS),
        fetcher=fetcher,
        user_urls=["https://www.user-source.example/article"],
    )
    assert len(bundle.user_source_pages) == 1
    stored = bundle.user_source_pages[0]
    assert stored.url == "https://www.user-source.example/article"
    assert stored.title == "User Article"
    assert "The company raised $10M" in stored.text


def test_gather_no_user_urls_produces_empty_user_pages() -> None:
    for user_urls in (None, []):
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
            user_urls=user_urls,
        )
        assert bundle.user_source_pages == []
