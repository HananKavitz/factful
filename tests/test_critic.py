from factful.agents.critic import (
    build_critic_prompt,
    critique,
    enforce_length_feedback,
    enforce_structure_feedback,
    reading_grade,
    word_count,
)
from factful.schemas import CritiqueReport, Draft, Issue


def test_reading_grade_simple_text_is_easier() -> None:
    simple = "The cat sat. The dog ran. The sun came up. We ate."
    complex = "The simultaneous precipitation of precipitation."
    assert reading_grade(simple) > reading_grade(complex)


def test_reading_grade_empty_text_is_zero() -> None:
    assert reading_grade("") == 0.0


def test_reading_grade_in_sane_range() -> None:
    grade = reading_grade("The market grew steadily throughout the long difficult quarter.")
    assert 0.0 <= grade <= 206.0


def test_word_count_counts_words_and_numbers() -> None:
    assert word_count("The market grew 12% [[c1]].") == 5


def test_word_count_empty_text_is_zero() -> None:
    assert word_count("") == 0


def test_build_critic_prompt_embeds_draft_and_grade() -> None:
    draft = Draft(title="Chips", markdown="Market grew 12% [[c1]].")
    prompt = build_critic_prompt(
        draft,
        reading_grade(draft.markdown),
        words=word_count(draft.markdown),
        min_words=900,
        max_words=1800,
    )
    assert "Market grew 12% [[c1]]." in prompt
    assert "Flesch" in prompt


def test_build_critic_prompt_embeds_word_count_and_bounds() -> None:
    draft = Draft(title="Chips", markdown="Market grew 12% [[c1]].")
    prompt = build_critic_prompt(
        draft, reading_grade(draft.markdown), words=5, min_words=900, max_words=1800
    )
    assert "word count: 5 words" in prompt
    assert "900" in prompt
    assert "1800" in prompt


def test_build_critic_prompt_includes_macro_arc_check() -> None:
    draft = Draft(title="Chips", markdown="Market grew 12% [[c1]].")
    prompt = build_critic_prompt(
        draft,
        reading_grade(draft.markdown),
        words=word_count(draft.markdown),
        min_words=900,
        max_words=1800,
    )
    assert "Macro-structure" in prompt
    assert "state-of-play" in prompt


def _facts_first_markdown() -> str:
    return "\n\n".join(
        [
            "Revenue hit $4B in 2024 [[c1]].",
            "The sector added 3,000 jobs [[c2]].",
            "Margins widened to 12% [[c3]].",
            "The analyst consensus sees no let-up.",
            "Our position remains strong.",
            "What will you do tomorrow?",
        ]
    )


def test_structure_gate_clean_facts_first_draft_unchanged() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    assert enforce_structure_feedback(report, markdown=_facts_first_markdown()) == report


def test_structure_gate_skips_short_drafts() -> None:
    report = CritiqueReport(score=80, issues=[], verdict="rework")
    markdown = "\n\n".join(["Market grew 12% [[c1]].", "Then it slowed.", "Now it is steady."])
    assert enforce_structure_feedback(report, markdown=markdown) == report


def test_structure_gate_flags_claim_in_clincher() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    markdown = "\n\n".join(
        [
            "Intro with the market growing 12% [[c1]].",
            "Revenue hit $4B in 2024 [[c2]].",
            "The sector added 3,000 jobs [[c3]].",
            "Margins expanded across the board.",
            "Competitors are catching up.",
            "The analyst consensus sees no let-up.",
            "Our position remains strong.",
            "The clock is ticking [[c1]].",
        ]
    )
    fixed = enforce_structure_feedback(report, markdown=markdown)
    structure = [i for i in fixed.issues if i.type == "Structure"]
    assert len(structure) == 1
    assert "closer" in structure[0].message
    assert structure[0].severity == "high"


def test_structure_gate_flags_late_facts() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    markdown = "\n\n".join(
        [
            "Revenue hit $4B in 2024 [[c1]].",
            "Margins widened to 12% [[c2]].",
            "The analyst consensus sees no let-up.",
            "Our position remains strong.",
            "Competitors are catching up.",
            "Nobody doubts our edge.",
            "Yet headcount reached 5,000 last year [[c3]].",
            "This is our conclusion.",
        ]
    )
    fixed = enforce_structure_feedback(report, markdown=markdown)
    structure = [i for i in fixed.issues if i.type == "Structure"]
    assert len(structure) == 1
    assert "late" in structure[0].message
    assert structure[0].severity == "high"


def test_structure_gate_flags_opinion_before_facts() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    markdown = "\n\n".join(
        [
            "We wander through the introduction.",
            "We speculate without evidence.",
            "We make grand claims of our own.",
            "Revenue hit $4B in 2024 [[c1]].",
            "The sector added 3,000 jobs [[c2]].",
            "Margins widened to 12% [[c3]].",
            "Headcount reached 5,000 [[c4]].",
            "This is our conclusion.",
        ]
    )
    fixed = enforce_structure_feedback(report, markdown=markdown)
    structure = [i for i in fixed.issues if i.type == "Structure"]
    assert len(structure) == 1
    assert "opinion" in structure[0].message
    assert structure[0].severity == "moderate"


def test_structure_gate_replaces_llm_structure_issues() -> None:
    report = CritiqueReport(
        score=80,
        verdict="rework",
        issues=[
            Issue(type="Structure", severity="moderate", message="scattered", revision="merge")
        ],
    )
    markdown = "\n\n".join(
        [
            "Intro with the market growing 12% [[c1]].",
            "Revenue hit $4B in 2024 [[c2]].",
            "The sector added 3,000 jobs [[c3]].",
            "Margins expanded across the board.",
            "Competitors are catching up.",
            "The analyst consensus sees no let-up.",
            "Our position remains strong.",
            "The clock is ticking [[c1]].",
        ]
    )
    fixed = enforce_structure_feedback(report, markdown=markdown)
    structure = [i for i in fixed.issues if i.type == "Structure"]
    assert len(structure) == 1
    assert all("scattered" not in (i.message or "") for i in fixed.issues)
    assert "closer" in structure[0].message


def test_critique_injects_structure_feedback() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    client = FakeClient(report)
    markdown = "\n\n".join(
        [
            "Revenue hit $4B in 2024 [[c1]].",
            "The sector added 3,000 jobs [[c2]].",
            "Margins widened to 12% [[c3]].",
            "The analyst consensus sees no let-up.",
            "Our position remains strong.",
            "The clock is ticking [[c1]].",
        ]
    )
    result = critique(Draft(title="Chips", markdown=markdown), client=client)
    assert any(i.type == "Structure" for i in result.issues)


class FakeClient:
    def __init__(self, report: CritiqueReport) -> None:
        self.report = report
        self.calls: list[tuple[str, type]] = []

    def chat_completion(self, *, prompt: str, schema: type) -> CritiqueReport:
        self.calls.append((prompt, schema))
        return self.report


def test_critique_returns_report() -> None:
    report = CritiqueReport(score=88, issues=[], verdict="pass")
    client = FakeClient(report)
    markdown = "The market grew steadily all year. " * 400
    draft = Draft(title="Chips", markdown=markdown)
    result = critique(draft, client=client)
    assert result == report
    assert client.calls[0][1] is CritiqueReport
    assert "The market grew" in client.calls[0][0]


def test_enforce_length_feedback_below_floor_orders_expansion() -> None:
    report = CritiqueReport(
        score=72,
        verdict="rework",
        issues=[
            Issue(
                type="Length",
                severity="moderate",
                message="exceeds the upper word count limit and feels padded",
                revision="Trim at least 300 words by cutting repetitive arguments.",
            )
        ],
    )
    fixed = enforce_length_feedback(report, words=1101, min_words=1500, max_words=2500)
    length_issues = [i for i in fixed.issues if i.type == "Length"]
    assert len(length_issues) == 1
    assert "below the minimum" in length_issues[0].message
    assert "Expand" in length_issues[0].revision
    assert all("Trim" not in (i.revision or "") for i in fixed.issues)


def test_enforce_length_feedback_above_ceiling_orders_trim() -> None:
    report = CritiqueReport(score=70, verdict="rework", issues=[])
    fixed = enforce_length_feedback(report, words=3000, min_words=1500, max_words=2500)
    length_issues = [i for i in fixed.issues if i.type == "Length"]
    assert len(length_issues) == 1
    assert "exceeds the maximum" in length_issues[0].message
    assert "Cut" in length_issues[0].revision


def test_enforce_length_feedback_within_range_unchanged() -> None:
    report = CritiqueReport(
        score=88,
        verdict="pass",
        issues=[Issue(type="Readability", severity="minor", message="flow could be smoother")],
    )
    fixed = enforce_length_feedback(report, words=2000, min_words=1500, max_words=2500)
    assert fixed == report


def test_critique_replaces_hallucinated_trim_advice_on_short_draft() -> None:
    short_draft = Draft(title="Chips", markdown="word " * 100)
    hallucinated = CritiqueReport(
        score=60,
        verdict="rework",
        issues=[
            Issue(
                type="Length",
                severity="high",
                message="exceeds the upper word count limit and feels padded",
                revision="Trim at least 300 words.",
            )
        ],
    )
    client = FakeClient(hallucinated)
    result = critique(short_draft, client=client)
    length_issues = [i for i in result.issues if i.type == "Length"]
    assert len(length_issues) == 1
    assert "below the minimum" in length_issues[0].message
    assert "Expand" in length_issues[0].revision
