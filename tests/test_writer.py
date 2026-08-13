from datetime import UTC, datetime

from factful.agents.writer import (
    build_revision_prompt,
    build_writer_prompt,
    extract_referenced_claims,
    revise_article,
    write_article,
)
from factful.schemas import (
    Citation,
    CritiqueReport,
    Draft,
    FactVerdict,
    Issue,
    SourceBundle,
)
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


def test_build_writer_prompt_includes_word_bounds() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "1500" in prompt
    assert "2000" in prompt
    assert "2500" in prompt
    assert "words" in prompt


def test_build_writer_prompt_includes_custom_instructions() -> None:
    prompt = build_writer_prompt(
        make_bundle(), profile(), instructions="Keep jargon minimal. Include a data table."
    )
    assert "Keep jargon minimal. Include a data table." in prompt


def test_build_writer_prompt_omits_instructions_section_when_none() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "Writer instructions:" not in prompt


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


def test_write_article_forwards_instructions() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    client = FakeClient(draft)
    write_article(make_bundle(), profile(), client=client, instructions="End with a CTA.")
    assert "End with a CTA." in client.calls[0][0]


def make_verdicts() -> list[FactVerdict]:
    return [
        FactVerdict(
            claim_id="c1",
            status="unverified",
            confidence=0.6,
            reason="single-source claim",
            suggested_revision="corroborate the figure with a second source",
        )
    ]


def make_critique() -> CritiqueReport:
    return CritiqueReport(
        score=70,
        issues=[
            Issue(
                type="hook",
                severity="high",
                message="weak opener",
                revision="open with a sharper statistic",
            )
        ],
        verdict="rework",
    )


def test_build_revision_prompt_includes_draft_feedback_and_bundle() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft, make_verdicts(), make_critique(), make_bundle(), profile()
    )
    assert "The market grew 12% [[c1]]." in prompt
    assert "single-source claim" in prompt
    assert "corroborate the figure with a second source" in prompt
    assert "weak opener" in prompt
    assert "sharper statistic" in prompt
    assert "Revenue hit $4B in 2024" in prompt
    assert "kevich" in prompt


def test_build_revision_prompt_includes_word_bounds() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft, make_verdicts(), make_critique(), make_bundle(), profile()
    )
    assert "1500" in prompt
    assert "2000" in prompt
    assert "2500" in prompt


def test_build_revision_prompt_includes_custom_instructions() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft,
        make_verdicts(),
        make_critique(),
        make_bundle(),
        profile(),
        instructions="Keep jargon minimal. Include a data table.",
    )
    assert "Keep jargon minimal. Include a data table." in prompt


def test_revise_article_returns_draft() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    revised = Draft(title="Chips", markdown="The market grew 12% [[c1]] — 15% in Europe.")
    client = FakeClient(revised)
    result = revise_article(
        draft, make_verdicts(), make_critique(), make_bundle(), profile(), client=client
    )
    assert result == revised
    assert client.calls[0][1] is Draft
    assert "The market grew 12% [[c1]]." in client.calls[0][0]
    assert "weak opener" in client.calls[0][0]


def test_revise_article_forwards_instructions() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    revised = Draft(title="Chips", markdown="The market grew 12% [[c1]] — 15% in Europe.")
    client = FakeClient(revised)
    revise_article(
        draft,
        make_verdicts(),
        make_critique(),
        make_bundle(),
        profile(),
        client=client,
        instructions="Keep jargon minimal.",
    )
    assert "Keep jargon minimal." in client.calls[0][0]
