"""Gather agent: expand topic into queries, gather and mine claims."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from urllib.parse import urlsplit

from factful.agents.fetch import Fetcher, Page
from factful.agents.search import Searcher, SearchResult
from factful.config import Settings
from factful.llm.client import ChatClient
from factful.schemas import (
    Citation,
    ClaimMineOutput,
    MinedClaim,
    QueryExpansion,
    RelevanceSelection,
    SourceBundle,
    UserSourcePage,
)

DEFAULT_MAX_SOURCES = 10
MAX_MINE_TEXT_CHARACTERS = 120_000

_SENTENCE_BOUNDARIES = (". ", ".\n", "\n")


def truncate_text(text: str, max_characters: int = MAX_MINE_TEXT_CHARACTERS) -> str:
    if len(text) <= max_characters:
        return text
    cut = text[:max_characters]
    for boundary in _SENTENCE_BOUNDARIES:
        index = cut.rfind(boundary)
        if index != -1:
            return cut[: index + 1].rstrip()
    return cut.rstrip()


_EXPANSION_INSTRUCTIONS = """
You are the gathering agent for a fact-grounded article. Expand the topic into
WEB-SEARCHABLE queries that would surface authoritative, recent sources carrying
specific numbers or statistics (market sizes, growth rates, counts, dollars).

Rules:
- Each query must be a distinct angle on the topic; no duplicated intent.
- Queries should be search-engine friendly: concrete, specific, number-seeking.
- Bias queries toward the current year and the latest available reporting; include
  the current year in queries where it helps surface fresh data.
- Return structured JSON matching the supplied schema.
"""

_MINE_INSTRUCTIONS = """
You are a claim miner. From the article below, extract ATOMIC factual claims, each
carrying exactly one specific number or statistic.

Rules:
- One claim per fact/stat. Do not merge several numbers into one claim.
- quote_snippet: copy the EXACT supporting sentence from the text verbatim. Never
  paraphrase, never abbreviate, never reword. If no literal sentence supports the
  number, skip that claim.
- key_stat: the salient numeric value only (e.g. "12%", "$4.2B", "3,000").
- Do not invent, guess, or extrapolate. Empty claims lists are acceptable when the
  article has no usable numbers.
- Return structured JSON matching the supplied schema.
"""

_RELEVANCE_INSTRUCTIONS = """
You are a claim screener. An article will be written about the Topic from the
given Angle, grounded strictly in the claims below. Decide which claims the writer
is allowed to use.

Keep ONLY claims that directly serve the topic and angle:
- The claim states or evidences something the angle will argue, or
- The claim supplies a figure the writer must anchor on (a market size, growth
  rate, count, or dollar figure central to the angle), or
- The claim is a supporting detail the argument genuinely builds on.

Reject claims that are tangential to the spine of the argument:
- Facts about a different industry, geography, or company that the topic and angle
  do not center on, e.g. a vendor's product metric or ROI anecdote in an article
  about a national sector.
- Figures that duplicate a stronger, more relevant claim.
- "Interesting but irrelevant" numbers that would read as asides.

When in doubt, reject: a focused article uses fewer, deeper claims. Return the
claim_ids to keep, listed in the same order they appear below. An empty list is
acceptable when no claim serves the topic and angle.
"""


def build_expand_prompt(topic: str, angle: str, *, today: date | None = None) -> str:
    today = today or date.today()
    return (
        f"Topic: {topic}\n"
        f"Angle: {angle}\n\n"
        f"Today is {today.isoformat()}.\n\n"
        f"Produce between 4 and 6 web-search queries.\n\n"
        f"{_EXPANSION_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(QueryExpansion.model_json_schema(), indent=2)}"
    )


def build_mine_prompt(page: Page) -> str:
    return (
        f"Article title: {page.title}\n"
        f"Article URL: {page.url}\n"
        f"Published: {page.publish_date or 'unknown'}\n\n"
        f"Text:\n{truncate_text(page.text)}\n\n"
        f"{_MINE_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(ClaimMineOutput.model_json_schema(), indent=2)}"
    )


def build_relevance_prompt(
    topic: str,
    angle: str,
    citations: list[Citation],
    *,
    today: date | None = None,
) -> str:
    today = today or date.today()
    lines = "\n".join(
        f"{index}. claim_id={c.claim_id} | claim={c.claim} | key_stat={c.key_stat} | "
        f"source={c.source_title} | publisher={c.publisher}"
        for index, c in enumerate(citations, start=1)
    )
    return (
        f"Topic: {topic}\n"
        f"Angle: {angle}\n\n"
        f"Today is {today.isoformat()}.\n\n"
        f"Candidate claims:\n{lines}\n\n"
        f"{_RELEVANCE_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(RelevanceSelection.model_json_schema(), indent=2)}"
    )


def expand_queries(
    topic: str,
    angle: str,
    *,
    client: ChatClient,
    today: date | None = None,
) -> list[str]:
    result = client.chat_completion(
        prompt=build_expand_prompt(topic, angle, today=today), schema=QueryExpansion
    )
    if not isinstance(result, QueryExpansion):
        raise TypeError(f"expected QueryExpansion, got {type(result).__name__}")
    return list(dict.fromkeys(result.queries))


def mine_claims(page: Page, *, client: ChatClient) -> list[MinedClaim]:
    if not page.text.strip():
        return []
    result = client.chat_completion(prompt=build_mine_prompt(page), schema=ClaimMineOutput)
    if not isinstance(result, ClaimMineOutput):
        raise TypeError(f"expected ClaimMineOutput, got {type(result).__name__}")
    return result.claims


def filter_relevant(
    citations: list[Citation],
    topic: str,
    angle: str,
    *,
    client: ChatClient,
    today: date | None = None,
) -> list[Citation]:
    if not citations:
        return citations
    prompt = build_relevance_prompt(topic, angle, citations, today=today)
    result = client.chat_completion(prompt=prompt, schema=RelevanceSelection)
    if not isinstance(result, RelevanceSelection):
        raise TypeError(f"expected RelevanceSelection, got {type(result).__name__}")
    keep = set(result.keep_claim_ids)
    return [citation for citation in citations if citation.claim_id in keep]


def dedupe_by_url(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for result in results:
        key = _normalize_url(result.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def find_passage_para(text: str, quote: str) -> str:
    paragraphs = [line for line in text.splitlines() if line.strip()]
    for index, paragraph in enumerate(paragraphs, start=1):
        if quote in paragraph:
            return f"para-{index}"
    return "para-0"


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}"


def _publisher_from_url(url: str) -> str:
    host = urlsplit(url).hostname or ""
    if host.startswith("www."):
        return host[4:]
    return host


def gather(
    topic: str,
    angle: str,
    *,
    client: ChatClient,
    searcher: Searcher,
    fetcher: Fetcher,
    settings: Settings | None = None,
    max_sources: int | None = None,
    today: date | None = None,
    user_urls: list[str] | None = None,
) -> SourceBundle:
    limit = max_sources
    if limit is None:
        limit = settings.gather.max_sources if settings is not None else DEFAULT_MAX_SOURCES

    # 1. Pre-fetch user-supplied URLs
    seen_urls: set[str] = set()
    citations: list[Citation] = []
    user_pages: list[UserSourcePage] = []
    next_id = 1
    if user_urls:
        for url in user_urls:
            norm = _normalize_url(url)
            if norm in seen_urls:
                continue
            seen_urls.add(norm)
            page = fetcher.fetch(url)
            if page is None:
                continue
            user_pages.append(UserSourcePage(url=page.url, title=page.title, text=page.text))
            for claim in mine_claims(page, client=client):
                citations.append(
                    Citation(
                        claim_id=f"c{next_id}",
                        claim=claim.claim,
                        source_url=page.url,
                        source_title=page.title,
                        publisher=_publisher_from_url(url),
                        publish_date=page.publish_date,
                        key_stat=claim.key_stat,
                        quote_snippet=claim.quote_snippet,
                        passage_ref=find_passage_para(page.text, claim.quote_snippet),
                        retrieved_at=datetime.now(UTC),
                    )
                )
                next_id += 1

    # 2. Search
    queries = expand_queries(topic, angle, client=client, today=today)
    results: list[SearchResult] = []
    for query in queries:
        results.extend(searcher.search(query))

    remaining = max(0, limit - len({c.source_url for c in citations}))
    for result in dedupe_by_url(results)[:remaining]:
        norm = _normalize_url(result.url)
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        page = fetcher.fetch(result.url)
        if page is None:
            continue
        for claim in mine_claims(page, client=client):
            citations.append(
                Citation(
                    claim_id=f"c{next_id}",
                    claim=claim.claim,
                    source_url=page.url,
                    source_title=page.title,
                    publisher=_publisher_from_url(result.url),
                    publish_date=page.publish_date,
                    key_stat=claim.key_stat,
                    quote_snippet=claim.quote_snippet,
                    passage_ref=find_passage_para(page.text, claim.quote_snippet),
                    retrieved_at=datetime.now(UTC),
                )
            )
            next_id += 1
    if not citations:
        raise ValueError(f"gather produced no citations for topic {topic!r}")
    focused = filter_relevant(citations, topic, angle, client=client, today=today)
    if not focused:
        focused = citations
    return SourceBundle(topic=topic, angle=angle, citations=focused, user_source_pages=user_pages)
