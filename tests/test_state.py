from factful.schemas import Citation, FactVerdict, SourceBundle
from factful.state import CRITICAL_STATUSES, PassRecord, PipelineState

VERIFIED = FactVerdict(claim_id="c1", status="verified", confidence=0.9, reason="ok")
CONTRADICTED = FactVerdict(claim_id="c1", status="contradicted", confidence=0.4, reason="x")


def make_state() -> PipelineState:
    citation = Citation(
        claim_id="c1",
        claim="x grew",
        source_url="https://e.com",
        source_title="t",
        publisher="p",
        publish_date="2025-01-01",
        key_stat="10%",
        quote_snippet="x grew",
        passage_ref="r",
        retrieved_at="2025-01-02T00:00:00Z",
    )
    return PipelineState(
        prompt="t",
        angle="a",
        source_bundle=SourceBundle(topic="t", angle="a", citations=[citation]),
    )


def test_initial_state() -> None:
    state = make_state()
    assert state.prompt == "t"
    assert state.angle == "a"
    assert state.draft is None
    assert state.score is None
    assert state.critical_failures == 0
    assert state.pass_ == 1
    assert state.verdicts == []
    assert state.critiques == []
    assert state.passes == []


def test_verdicts_track_critical_failures() -> None:
    state = make_state()
    state.add_verdict(VERIFIED)
    assert state.critical_failures == 0
    state.add_verdict(CONTRADICTED)
    assert state.critical_failures == 1


def test_record_pass_snapshots_into_history() -> None:
    state = make_state()
    state.add_verdict(CONTRADICTED)
    state.record_pass(score=80.0, draft="text")
    assert state.score == 80.0
    assert state.draft == "text"
    assert state.passes == [PassRecord(score=80.0, draft="text", critical_failures=1)]


def test_advance_pass_clears_per_pass_accumulators() -> None:
    state = make_state()
    state.add_verdict(CONTRADICTED)
    state.record_pass(score=70.0, draft="draft-1")
    state.advance_pass()
    assert state.pass_ == 2
    assert state.verdicts == []
    assert state.critiques == []
    assert state.critical_failures == 0


def test_critical_failures_only_count_current_pass() -> None:
    state = make_state()
    state.add_verdict(CONTRADICTED)
    state.record_pass(score=70.0, draft="draft-1")
    state.advance_pass()
    state.add_verdict(VERIFIED)
    assert state.critical_failures == 0
    assert state.passes[0].critical_failures == 1


def test_citations_are_copied_not_shared() -> None:
    citation = Citation(
        claim_id="c1",
        claim="x",
        source_url="https://e.com",
        source_title="t",
        publisher="p",
        publish_date="2025-01-01",
        key_stat="10%",
        quote_snippet="x",
        passage_ref="r",
        retrieved_at="2025-01-02T00:00:00Z",
    )
    bundle = SourceBundle(topic="t", angle="a", citations=[citation])
    state = PipelineState(prompt="t", angle="a", source_bundle=bundle)
    bundle.citations.clear()
    assert state.citations == [citation]
