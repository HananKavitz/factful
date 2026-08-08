from datetime import UTC, datetime

from factful.agents.writer import (
    build_writer_prompt,
    extract_referenced_claims,
    write_article,
)
from factful.schemas import Citation, Draft, SourceBundle
from factful.style.io import load_profile
from factful.style.schema import StyleProfile


def make_bundle() -> SourceBundle:
    citations = [
        Citation(
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
    ]
    return SourceBundle(topic="Semiconductors", angle="supply risk", citations=citations)


def profile() -> StyleProfile:
    return load_profile("src/factful/style/profiles/kevich.yaml")


def test_build_writer_prompt_embeds_bundle_and_profile() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "Semiconductors" in prompt
    assert "c1" in prompt
    assert "Revenue hit $4B in 2024" in prompt
    assert "kevich" in prompt
    assert "[[claim_id]]" in prompt


def test_extract_referenced_claims_in_order_deduplicated() -> None:
    md = "Intro. [[c1]] and more [[c2]], then [[c1]] again."
    assert extract_referenced_claims(md) == ["c1", "c2"]


def test_extract_referenced_claims_none() -> None:
    assert extract_referenced_claims("no tags here") == []


class FakeClient:
    def __init__(self, draft: Draft) -> None:
        self.draft = draft
        self.calls: list[tuple[str, type]] = []

    def chat_completion(self, *, prompt: str, schema: type) -> Draft:
        self.calls.append((prompt, schema))
        return self.draft


def test_write_article_returns_draft() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    client = FakeClient(draft)
    result = write_article(make_bundle(), profile(), client=client)
    assert result == draft
    assert client.calls[0][1] is Draft
    assert "kevich" in client.calls[0][0]
