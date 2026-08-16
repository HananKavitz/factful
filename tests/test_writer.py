from datetime import UTC, date, datetime

from factful.agents.writer import (
    apply_user_edit,
    build_revision_prompt,
    build_user_edit_prompt,
    build_writer_prompt,
    extract_referenced_claims,
    normalize_paragraphs,
    revise_article,
    strip_claim_tags,
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
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile


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


def custom_profile(
    *, avg_paragraph_sentences: float = 3.0, paragraph_length_dist: list[int] | None = None
) -> StyleProfile:
    return StyleProfile(
        name="kevich",
        metrics=StyleMetrics(
            avg_sentence_words=16.0,
            avg_paragraph_sentences=avg_paragraph_sentences,
            paragraph_length_dist=paragraph_length_dist or [],
        ),
        extraction=StyleExtraction(voice="long-form, opinionated", tone="acerbic, skeptical"),
    )


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


def test_build_writer_prompt_includes_structure_contract() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "State of play" in prompt
    assert "Diagnosis" in prompt
    assert "Recommended action plan" in prompt


def test_build_writer_prompt_includes_paragraph_length_guidance() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "Paragraphs —" in prompt
    assert "4 sentences" in prompt
    assert "2-7 sentences" in prompt
    assert "two or fewer" in prompt


def test_build_writer_prompt_injects_today_date() -> None:
    prompt = build_writer_prompt(make_bundle(), profile(), today=date(2026, 8, 13))
    assert "Today is 2026-08-13" in prompt


def test_build_writer_prompt_defaults_to_current_date() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert f"Today is {date.today().isoformat()}" in prompt


def test_build_writer_prompt_warns_against_presenting_stale_data_as_current() -> None:
    prompt = build_writer_prompt(make_bundle(), profile(), today=date(2026, 8, 13))
    assert "as of" in prompt.lower()


def test_build_writer_prompt_includes_custom_instructions() -> None:
    prompt = build_writer_prompt(
        make_bundle(), profile(), instructions="Keep jargon minimal. Include a data table."
    )
    assert "Keep jargon minimal. Include a data table." in prompt


def test_build_writer_prompt_omits_instructions_section_when_none() -> None:
    prompt = build_writer_prompt(make_bundle(), profile())
    assert "Writer instructions:" not in prompt


def test_build_writer_prompt_omits_instructions_section_when_empty() -> None:
    prompt = build_writer_prompt(make_bundle(), profile(), instructions="")
    assert "Writer instructions:" not in prompt


def test_build_writer_prompt_omits_whitespace_only_instructions() -> None:
    prompt = build_writer_prompt(make_bundle(), profile(), instructions=" \t \n ")
    assert "Writer instructions:" not in prompt


def test_build_writer_prompt_strips_instructions_whitespace() -> None:
    prompt = build_writer_prompt(make_bundle(), profile(), instructions="  Keep jargon minimal.  ")
    assert "Writer instructions:\nKeep jargon minimal.\n\n" in prompt
    assert "  Keep jargon minimal.  " not in prompt


def test_extract_referenced_claims_in_order_deduplicated() -> None:
    md = "Intro. [[c1]] and more [[c2]], then [[c1]] again."
    assert extract_referenced_claims(md) == ["c1", "c2"]


def test_extract_referenced_claims_none() -> None:
    assert extract_referenced_claims("no tags here") == []


def test_strip_claim_tags_removes_tag_before_period() -> None:
    assert strip_claim_tags("The market grew 12% [[c1]].") == "The market grew 12%."


def test_strip_claim_tags_removes_tag_mid_sentence() -> None:
    assert (
        strip_claim_tags("Revenue hit $4B [[c1]], while margins widened [[c2]].")
        == "Revenue hit $4B, while margins widened."
    )


def test_strip_claim_tags_removes_all_repeated_tags() -> None:
    assert strip_claim_tags("[[c1]] lead. Repeat the stat [[c1]] and cite again [[c17]].") == (
        "lead. Repeat the stat and cite again."
    )


def test_strip_claim_tags_preserves_paragraph_structure() -> None:
    md = "State of play [[c1]].\n\nDiagnosis, pure opinion."
    assert strip_claim_tags(md) == "State of play.\n\nDiagnosis, pure opinion."


def test_strip_claim_tags_noop_without_tags() -> None:
    assert strip_claim_tags("Pure opinion, no numbers here.") == "Pure opinion, no numbers here."


def test_normalize_paragraphs_leaves_existing_blank_line_paragraphs_untouched() -> None:
    md = "# Title\n\nFirst paragraph here.\n\nSecond paragraph here.\n\n- a\n- b"
    assert normalize_paragraphs(md, profile=profile()) == md


def test_normalize_paragraphs_returns_unchanged_when_empty() -> None:
    assert normalize_paragraphs("", profile=profile()) == ""


def test_normalize_paragraphs_splits_collapsed_text_into_paragraphs() -> None:
    md = "One sentence. Two sentence. Three sentence. Four sentence. Five sentence."
    result = normalize_paragraphs(md, profile=custom_profile(avg_paragraph_sentences=3.0))
    assert result == "One sentence. Two sentence. Three sentence.\n\nFour sentence. Five sentence."


def test_normalize_paragraphs_does_not_break_decimal_numbers() -> None:
    md = "Revenue hit $53.43 billion in 2025. It is set to expand at a 2.95% CAGR."
    result = normalize_paragraphs(md, profile=custom_profile(avg_paragraph_sentences=2.0))
    assert "$53.43 billion" in result
    assert "2.95% CAGR" in result


def test_normalize_paragraphs_paces_to_profile_distribution() -> None:
    md = "S1. S2. S3. S4. S5. S6. S7. S8."
    result = normalize_paragraphs(md, profile=custom_profile(paragraph_length_dist=[2, 3]))
    assert result.split("\n\n") == ["S1. S2.", "S3. S4. S5.", "S6. S7.", "S8."]


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


def test_write_article_normalizes_collapsed_markdown() -> None:
    collapsed = Draft(title="Chips", markdown="Market grew. It grew again. It kept growing.")
    client = FakeClient(collapsed)
    result = write_article(make_bundle(), profile(), client=client)
    assert "\n\n" in result.markdown


def test_revise_article_normalizes_collapsed_markdown() -> None:
    collapsed = Draft(title="Chips", markdown="Fixed the lead. Fixed the middle. Fixed the end.")
    client = FakeClient(collapsed)
    result = revise_article(
        Draft(title="Chips", markdown="Old."),
        make_verdicts(),
        make_critique(),
        make_bundle(),
        profile(),
        client=client,
    )
    assert "\n\n" in result.markdown


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


def test_build_revision_prompt_allows_restructuring() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft, make_verdicts(), make_critique(), make_bundle(), profile()
    )
    assert "restructure" in prompt
    assert "Keep the voice, structure" not in prompt


def test_build_revision_prompt_includes_word_bounds() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft, make_verdicts(), make_critique(), make_bundle(), profile()
    )
    assert "1500" in prompt
    assert "2000" in prompt
    assert "2500" in prompt


def test_build_revision_prompt_includes_paragraph_length_guidance() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft, make_verdicts(), make_critique(), make_bundle(), profile()
    )
    assert "Paragraphs —" in prompt
    assert "4 sentences" in prompt
    assert "two or fewer" in prompt


def test_build_revision_prompt_injects_today_date() -> None:
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    prompt = build_revision_prompt(
        draft,
        make_verdicts(),
        make_critique(),
        make_bundle(),
        profile(),
        today=date(2026, 8, 13),
    )
    assert "Today is 2026-08-13" in prompt


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


def test_build_user_edit_prompt_includes_markdown_instruction_and_profile() -> None:
    prompt = build_user_edit_prompt(
        "Chips are scarce.\n\nDemand is rising.", "Shorten the lead", profile()
    )
    assert "Chips are scarce." in prompt
    assert "Shorten the lead" in prompt
    assert "kevich" in prompt


def test_build_user_edit_prompt_injects_today_date() -> None:
    prompt = build_user_edit_prompt(
        "Chips are scarce.",
        "Add a closing line",
        profile(),
        today=date(2026, 8, 13),
    )
    assert "Today is 2026-08-13" in prompt


def test_apply_user_edit_returns_draft_and_preserves_scope() -> None:
    edited = Draft(title="Chips", markdown="Chips are scarce.\n\nDemand is rising sharply.")
    client = FakeClient(edited)
    result = apply_user_edit(
        "Chips are scarce.\n\nDemand is rising.",
        "Make demand sound sharper",
        profile(),
        client=client,
    )
    assert result == edited
    assert client.calls[0][1] is Draft
    prompt = client.calls[0][0]
    assert "Chips are scarce." in prompt
    assert "Make demand sound sharper" in prompt
    assert "Change ONLY what the instruction asks for" in prompt


def test_apply_user_edit_normalizes_collapsed_markdown() -> None:
    collapsed = Draft(title="Chips", markdown="Fixed the lead. Fixed the middle. Fixed the end.")
    client = FakeClient(collapsed)
    result = apply_user_edit("Chips are scarce.", "Tighten the prose", profile(), client=client)
    assert "\n\n" in result.markdown
