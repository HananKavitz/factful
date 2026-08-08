from datetime import UTC, datetime

from factful.schemas import AttributionVerdict, Citation
from factful.verify.judge import build_attribution_prompt, judge_claim

CITATION = Citation(
    claim_id="c1",
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


class FakeJudge:
    def __init__(self, verdict: AttributionVerdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, type]] = []

    def chat_completion(self, *, prompt: str, schema: type) -> AttributionVerdict:
        self.calls.append((prompt, schema))
        return self.verdict


def test_judge_prompt_embeds_claim_and_passage() -> None:
    prompt = build_attribution_prompt(
        claim="Revenue hit $4B in 2024",
        key_stat="$4B",
        source_url="https://example.com/report",
        source_title="Annual Report",
        passage="Revenue hit $4B in 2024.",
        passage_ref="sentence-2",
    )
    assert "Revenue hit $4B in 2024" in prompt
    assert "Revenue hit $4B in 2024." in prompt
    assert "sentence-2" in prompt
    assert "closed" in prompt.lower() or "prior knowledge" in prompt.lower()


def test_judge_claim_passes_citation_to_prompt() -> None:
    client = FakeJudge(AttributionVerdict(status="supported", confidence=0.99, reason="ok"))
    result = judge_claim(CITATION, "Revenue hit $4B in 2024.", "sentence-2", client=client)
    assert result.status == "supported"
    assert result.confidence == 0.99
    assert len(client.calls) == 1
    prompt = client.calls[0][0]
    assert "Revenue hit $4B in 2024" in prompt
    assert client.calls[0][1] is AttributionVerdict


def test_judge_passes_through_unsupported() -> None:
    client = FakeJudge(
        AttributionVerdict(status="unsupported", confidence=0.3, reason="not in passage")
    )
    result = judge_claim(CITATION, "unrelated sentence", "sentence-1", client=client)
    assert result.status == "unsupported"
    assert "not in passage" in result.reason
