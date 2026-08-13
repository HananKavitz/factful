"""Fact-check agent: verify every claim referenced by a draft against its sources."""

from __future__ import annotations

from datetime import date

from factful.agents.fetch import Fetcher
from factful.agents.writer import extract_referenced_claims
from factful.config import Settings
from factful.llm.client import ChatClient
from factful.schemas import Citation, Draft, FactVerdict
from factful.verify.bm25 import Bm25Scorer
from factful.verify.corroborate import contradicting_sources, corroborating_sources
from factful.verify.gates import numeric_gates
from factful.verify.judge import judge_claim
from factful.verify.passages import split_passages


def _passage_ref(index: int) -> str:
    return f"sentence-{index + 1}"


def _verify_citation(
    citation: Citation,
    citations: list[Citation],
    *,
    fetcher: Fetcher,
    client: ChatClient,
    settings: Settings,
    today: date | None,
) -> FactVerdict:
    min_sources = settings.corroboration.min_sources
    flags: list[str] = numeric_gates(
        citation.claim,
        citation.key_stat,
        citation.quote_snippet,
        citation.publish_date,
        settings.verify.max_currency_years,
        today=today,
    )
    unsupported = FactVerdict(
        claim_id=citation.claim_id,
        status="unsupported",
        confidence=0.0,
        reason="",
        flags=flags,
    )

    page = fetcher.fetch(citation.source_url)
    if page is None:
        unsupported.reason = "source page could not be fetched"
        return unsupported

    passages = split_passages(page.text)
    if not passages:
        unsupported.reason = "source page has no retrievable content"
        return unsupported

    hits = Bm25Scorer(passages=passages).retrieve(
        citation.claim, k=settings.retrieval.top_k_passages
    )
    if not hits:
        unsupported.reason = "no passage retrievable for the claim"
        return unsupported
    best = hits[0]

    verdict = judge_claim(citation, best.passage, _passage_ref(best.index), client=client)
    if verdict.status == "unsupported":
        return FactVerdict(
            claim_id=citation.claim_id,
            status="unverified",
            confidence=verdict.confidence,
            reason=verdict.reason,
            flags=flags,
        )

    conflicting = contradicting_sources(citations, citation)
    if conflicting:
        return FactVerdict(
            claim_id=citation.claim_id,
            status="contradicted",
            confidence=verdict.confidence,
            reason=f"sources disagree on the value: {', '.join(conflicting)}",
            flags=flags,
        )

    corroborated = corroborating_sources(citations, citation)
    if len(corroborated) + 1 >= min_sources:
        return FactVerdict(
            claim_id=citation.claim_id,
            status="verified",
            confidence=verdict.confidence,
            reason=verdict.reason,
            corroborations=corroborated,
            flags=flags,
        )
    return FactVerdict(
        claim_id=citation.claim_id,
        status="unverified",
        confidence=verdict.confidence,
        reason=f"single-source claim; needs {min_sources} independent sources",
        corroborations=corroborated,
        flags=flags,
    )


def factcheck_article(
    draft: Draft,
    citations: list[Citation],
    *,
    fetcher: Fetcher,
    client: ChatClient,
    settings: Settings | None = None,
    today: date | None = None,
) -> list[FactVerdict]:
    settings = settings if settings is not None else Settings()
    by_id = {c.claim_id: c for c in citations}
    verdicts: list[FactVerdict] = []
    for claim_id in extract_referenced_claims(draft.markdown):
        citation = by_id.get(claim_id)
        if citation is None:
            verdicts.append(
                FactVerdict(
                    claim_id=claim_id,
                    status="unsupported",
                    confidence=0.0,
                    reason="claim not present in the source bundle",
                )
            )
            continue
        verdicts.append(
            _verify_citation(
                citation,
                citations,
                fetcher=fetcher,
                client=client,
                settings=settings,
                today=today,
            )
        )
    return verdicts
