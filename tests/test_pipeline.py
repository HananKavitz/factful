import logging
from datetime import UTC, datetime

import pytest

from factful.agents.fetch import Page
from factful.agents.search import SearchResult
from factful.config import Settings
from factful.pipeline import (
    ConvergeResult,
    PipelineClients,
    converge,
    run_pipeline,
)
from factful.schemas import (
    AttributionVerdict,
    Citation,
    ClaimMineOutput,
    CritiqueReport,
    Draft,
    MinedClaim,
    QueryExpansion,
)
from factful.state import PassRecord
from factful.style.io import load_profile


def settings() -> Settings:
    return Settings()


def profile():
    return load_profile("src/factful/style/profiles/kevich.yaml")


def citation(c1: str = "c1") -> Citation:
    return Citation(
        claim_id=c1,
        claim="Revenue hit $4B in 2024",
        source_url="https://example.com/report",
        source_title="Annual Report",
        publisher="example.com",
        publish_date="2024-01-01",
        key_stat="$4B",
        quote_snippet="Revenue hit $4B in 2024.",
        passage_ref="para-2",
        retrieved_at=datetime(2024, 1, 2, tzinfo=UTC),
    )


class FakeClient:
    def __init__(
        self,
        drafts: list[Draft] | None = None,
        scores: list[int] | None = None,
    ) -> None:
        self.drafts = list(drafts) if drafts else []
        self.scores = list(scores) if scores else []
        self.calls: list[tuple[str, type]] = []

    def chat_completion(self, *, prompt: str, schema: type):
        self.calls.append((prompt, schema))
        if schema is QueryExpansion:
            return QueryExpansion(queries=["q1", "q2", "q3", "q4"])
        if schema is ClaimMineOutput:
            claim = MinedClaim(
                claim="Revenue hit $4B in 2024",
                key_stat="$4B",
                quote_snippet="Revenue hit $4B in 2024.",
            )
            return ClaimMineOutput(claims=[claim])
        if schema is Draft:
            return self.drafts.pop(0)
        if schema is AttributionVerdict:
            return AttributionVerdict(status="supported", confidence=0.9, reason="passage matches")
        if schema is CritiqueReport:
            return CritiqueReport(score=self.scores.pop(0), issues=[], verdict="rework")
        raise AssertionError(f"unexpected schema: {schema}")


class FakeSearcher:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = (
            results
            if results is not None
            else [SearchResult(url=citation().source_url, title="Annual Report")]
        )

    def search(self, query: str) -> list[SearchResult]:
        return self.results


class FakeFetcher:
    def __init__(self, page: Page | None = None) -> None:
        self.page = page or Page(
            url=citation().source_url,
            title="Annual Report",
            publish_date="2024-01-01",
            text="Revenue hit $4B in 2024. The market grew sharply. Analysts expect more growth.",
        )

    def fetch(self, url: str) -> Page | None:
        return self.page


def clients(client: FakeClient) -> PipelineClients:
    return PipelineClients(
        gather=client,
        writer=client,
        factcheck=client,
        critic=client,
    )


def draft(text: str = "Revenue hit $4B in 2024 [[c1]].") -> Draft:
    return Draft(title="Chips", markdown=text)


def test_converge_publishes_on_hard_gate() -> None:
    result = converge(
        score=90,
        critical_failures=0,
        pass_=1,
        settings=settings(),
        history=[],
    )
    assert result == ConvergeResult(decision="publish", reason="hard gate passed")


def test_converge_patches_when_below_gate() -> None:
    result = converge(
        score=80,
        critical_failures=0,
        pass_=1,
        settings=settings(),
        history=[],
    )
    assert result.decision == "patch"


def test_converge_stops_on_oscillation() -> None:
    result = converge(
        score=80,
        critical_failures=0,
        pass_=2,
        settings=settings(),
        history=[PassRecord(score=85, draft="d", critical_failures=0)],
    )
    assert result.decision == "stop"
    assert "regressed" in result.reason


def test_converge_stops_on_diminishing_returns() -> None:
    result = converge(
        score=84.5,
        critical_failures=0,
        pass_=2,
        settings=settings(),
        history=[PassRecord(score=84, draft="d", critical_failures=0)],
    )
    assert result.decision == "stop"
    assert "diminishing" in result.reason


def test_converge_continues_while_improving() -> None:
    result = converge(
        score=82,
        critical_failures=0,
        pass_=2,
        settings=settings(),
        history=[PassRecord(score=80, draft="d", critical_failures=0)],
    )
    assert result.decision == "patch"


def test_converge_stops_at_max_passes_cap() -> None:
    result = converge(
        score=70,
        critical_failures=1,
        pass_=3,
        settings=settings(),
        history=[
            PassRecord(score=60, draft="d1", critical_failures=1),
            PassRecord(score=65, draft="d2", critical_failures=1),
        ],
    )
    assert result.decision == "stop"
    assert "max passes" in result.reason


def test_converge_hard_gate_beats_cap() -> None:
    result = converge(
        score=90,
        critical_failures=0,
        pass_=3,
        settings=settings(),
        history=[
            PassRecord(score=80, draft="d1", critical_failures=0),
            PassRecord(score=85, draft="d2", critical_failures=0),
        ],
    )
    assert result.decision == "publish"


def test_run_pipeline_single_pass_publishes() -> None:
    client = FakeClient(drafts=[draft()], scores=[90])
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision == "publish"
    assert result.reason == "hard gate passed"
    assert result.state.pass_ == 1
    assert len(result.state.passes) == 1
    assert result.state.draft == "Revenue hit $4B in 2024 [[c1]]."
    assert result.state.score == 90
    assert len(result.state.verdicts) == 1
    assert result.unresolved == []


def test_run_pipeline_logs_progress(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="factful.pipeline")
    client = FakeClient(drafts=[draft()], scores=[90])
    run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    messages = [record.message for record in caplog.records]
    assert any("gathered 1 citations" in m for m in messages)
    assert any("pass 1: wrote draft" in m for m in messages)
    assert any("pass 1: fact-checked 1 claims" in m for m in messages)
    assert any("pass 1: critique score 90" in m for m in messages)
    assert any("decision: publish (hard gate passed)" in m for m in messages)


def test_run_pipeline_patches_until_hard_gate() -> None:
    client = FakeClient(
        drafts=[draft("weak draft [[c1]]"), draft("better draft [[c1]]")], scores=[70, 90]
    )
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision == "publish"
    assert result.state.pass_ == 2
    assert len(result.state.passes) == 2
    assert result.state.draft == "better draft [[c1]]"
    draft_calls = [prompt for prompt, schema in client.calls if schema is Draft]
    assert len(draft_calls) == 2
    assert "Current draft:" in draft_calls[1]


def test_run_pipeline_passes_instructions_to_writer_every_pass() -> None:
    client = FakeClient(
        drafts=[draft("weak draft [[c1]]"), draft("better draft [[c1]]")], scores=[70, 90]
    )
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
        instructions="Keep jargon minimal. End with a CTA.",
    )
    assert result.decision == "publish"
    draft_calls = [prompt for prompt, schema in client.calls if schema is Draft]
    assert len(draft_calls) == 2
    assert all("Keep jargon minimal. End with a CTA." in prompt for prompt in draft_calls)


def test_run_pipeline_regenerate_mode_rewrites_each_pass() -> None:
    cfg = Settings()
    cfg.pipeline.revision_mode = "regenerate"
    client = FakeClient(drafts=[draft("first [[c1]]"), draft("second [[c1]]")], scores=[70, 90])
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=cfg,
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision == "publish"
    draft_calls = [prompt for prompt, schema in client.calls if schema is Draft]
    assert len(draft_calls) == 2
    assert "Current draft:" not in draft_calls[1]


def test_run_pipeline_stops_at_max_passes_cap() -> None:
    client = FakeClient(
        drafts=[draft(f"d{i} [[c1]]") for i in range(3)],
        scores=[60, 70, 80],
    )
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision == "stop"
    assert result.state.pass_ == 3
    assert len(result.state.passes) == 3


def test_run_pipeline_keeps_best_draft_on_oscillation() -> None:
    client = FakeClient(
        drafts=[draft("best draft [[c1]]"), draft("regressed draft [[c1]]")], scores=[84, 60]
    )
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision == "stop"
    assert "regressed" in result.reason
    assert result.state.draft == "best draft [[c1]]"


def test_run_pipeline_reports_unresolved_critical_claims() -> None:
    unrelated_fetcher = FakeFetcher(
        page=Page(
            url=citation().source_url,
            title="Annual Report",
            publish_date="2024-01-01",
            text="The economy is doing fine. Everything is going great.",
        )
    )
    client = FakeClient(drafts=[draft(), draft()], scores=[70, 70])
    result = run_pipeline(
        "Semiconductors",
        "supply risk",
        settings=settings(),
        searcher=FakeSearcher(),
        fetcher=unrelated_fetcher,
        clients=clients(client),
        profile=profile(),
    )
    assert result.decision != "publish"
    assert len(result.unresolved) == 1
    assert result.unresolved[0].claim_id == "c1"
    assert result.unresolved[0].status == "unsupported"


def test_run_pipeline_raises_when_gather_yields_nothing() -> None:
    client = FakeClient(drafts=[draft()], scores=[90])
    with pytest.raises(ValueError, match="gather produced no citations"):
        run_pipeline(
            "Semiconductors",
            "supply risk",
            settings=settings(),
            searcher=FakeSearcher(results=[]),
            fetcher=FakeFetcher(),
            clients=clients(client),
            profile=profile(),
        )
