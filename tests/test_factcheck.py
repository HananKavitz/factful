from datetime import UTC, datetime

from pydantic import BaseModel

from factful.agents.factcheck import factcheck_article
from factful.agents.fetch import Page
from factful.config import Settings
from factful.schemas import AttributionVerdict, Citation, Draft, FactVerdict

SOURCE = "https://example.com/report"
OBSERVED = "https://example.com/report-b"

GOOD_PAGE = Page(
    url=SOURCE,
    title="Report",
    publish_date="2024-01-01",
    text="The firm said revenue hit $4B in 2024. Analysts expect steady growth.",
)


def make_citation(claim_id: str, key_stat: str, url: str = SOURCE) -> Citation:
    return Citation(
        claim_id=claim_id,
        claim=f"Revenue hit {key_stat} in 2024",
        source_url=url,
        source_title="Annual Report",
        publisher="example.com",
        publish_date="2024-01-01",
        key_stat=key_stat,
        quote_snippet=f"Revenue hit {key_stat} in 2024.",
        passage_ref="para-2",
        retrieved_at=datetime(2024, 1, 2, tzinfo=UTC),
    )


def make_draft(markdown: str) -> Draft:
    return Draft(title="Chips", markdown=markdown)


def supported() -> AttributionVerdict:
    return AttributionVerdict(status="supported", confidence=0.9, reason="ok")


def rejected() -> AttributionVerdict:
    return AttributionVerdict(status="unsupported", confidence=0.2, reason="no match")


class FakeFetcher:
    def __init__(self, pages: dict[str, Page]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> Page | None:
        return self.pages.get(url)


class FakeClient:
    def __init__(self, verdict: AttributionVerdict) -> None:
        self.verdict = verdict

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        return self.verdict


def run(
    draft: Draft,
    citations: list[Citation],
    *,
    pages: dict[str, Page] | None = None,
    verdict: AttributionVerdict | None = None,
    settings: Settings | None = None,
) -> list[FactVerdict]:
    client = FakeClient(verdict or supported())
    fetcher = FakeFetcher(pages if pages is not None else {SOURCE: GOOD_PAGE})
    return factcheck_article(draft, citations, fetcher=fetcher, client=client, settings=settings)


def test_checks_only_referenced_claims() -> None:
    draft = make_draft("Only c1 here [[c1]].")
    citations = [make_citation("c1", "$4B"), make_citation("c2", "27%")]
    verdicts = run(draft, citations)
    assert [v.claim_id for v in verdicts] == ["c1"]


def test_missing_claim_in_bundle_is_unsupported() -> None:
    draft = make_draft("Unknown [[c9]].")
    verdicts = run(draft, [])
    assert verdicts[0].status == "unsupported"
    assert "not present" in verdicts[0].reason


def test_fetch_failure_is_unsupported() -> None:
    draft = make_draft("Claim [[c1]].")
    citations = [make_citation("c1", "$4B")]
    verdicts = run(draft, citations, pages={})
    assert verdicts[0].status == "unsupported"
    assert "could not be fetched" in verdicts[0].reason


def test_no_retrievable_passage_is_unsupported() -> None:
    empty = Page(url=SOURCE, title="Empty", publish_date="", text="")
    draft = make_draft("Claim [[c1]].")
    verdicts = run(draft, [make_citation("c1", "$4B")], pages={SOURCE: empty})
    assert verdicts[0].status == "unsupported"
    assert "no retrievable content" in verdicts[0].reason


def test_judge_unsupported_cannot_be_verified() -> None:
    draft = make_draft("Claim [[c1]].")
    verdicts = run(
        draft,
        [make_citation("c1", "$4B")],
        verdict=rejected(),
    )
    assert verdicts[0].status == "unverified"
    assert "no match" in verdicts[0].reason


def test_source_conflict_is_contradicted() -> None:
    draft = make_draft("Claim [[c1]].")
    citations = [
        make_citation("c1", "$4B"),
        make_citation("c2", "$5B", url=OBSERVED),
        make_citation("c3", "$4B", url="https://example.com/report-c"),
    ]
    verdicts = run(draft, citations)
    assert verdicts[0].status == "contradicted"
    assert verdicts[0].corroborations == []


def test_contradiction_wins_over_corroboration() -> None:
    draft = make_draft("Claim [[c1]].")
    citations = [
        make_citation("c1", "$4B"),
        make_citation("c2", "$4B", url=OBSERVED),
        make_citation("c3", "$5B", url="https://example.com/report-c"),
    ]
    verdicts = run(draft, citations)
    assert verdicts[0].status == "contradicted"


def test_multiple_claims_mixed_statuses() -> None:
    draft = make_draft("Verified [[c1]] and unverified [[c3]].")
    citations = [
        make_citation("c1", "$4B"),
        make_citation("c1b", "$4B", url=OBSERVED),
        make_citation("c3", "27%", url="https://example.com/report-c"),
    ]
    verdicts = run(
        draft,
        citations,
        pages={SOURCE: GOOD_PAGE, "https://example.com/report-c": GOOD_PAGE},
    )
    by_id = {v.claim_id: v for v in verdicts}
    assert by_id["c1"].status == "verified"
    assert by_id["c3"].status == "unverified"


def test_supported_with_corroboration_is_verified() -> None:
    draft = make_draft("Claim [[c1]].")
    citations = [
        make_citation("c1", "$4B"),
        make_citation("c2", "$4B", url=OBSERVED),
    ]
    verdicts = run(draft, citations)
    assert verdicts[0].status == "verified"
    assert verdicts[0].corroborations == [OBSERVED]


def test_supported_single_source_unverified() -> None:
    draft = make_draft("Claim [[c1]].")
    verdicts = run(draft, [make_citation("c1", "$4B")])
    assert verdicts[0].status == "unverified"
    assert "single-source" in verdicts[0].reason


def test_flags_include_stale_source() -> None:
    stale = Page(url=SOURCE, title="Old", publish_date="2010-01-01", text="old data here.")
    settings = Settings(verify={"max_currency_years": 1.0})
    draft = make_draft("Claim [[c1]].")
    verdicts = run(draft, [make_citation("c1", "$4B")], pages={SOURCE: stale}, settings=settings)
    assert any("years old" in flag for flag in verdicts[0].flags)
