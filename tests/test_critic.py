from factful.agents.critic import build_critic_prompt, critique, reading_grade, word_count
from factful.schemas import CritiqueReport, Draft


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
    draft = Draft(title="Chips", markdown="The market grew 12% [[c1]].")
    result = critique(draft, client=client)
    assert result == report
    assert client.calls[0][1] is CritiqueReport
    assert "The market grew" in client.calls[0][0]
