from __future__ import annotations

from factful.style.deterministic import (
    detect_openers,
    detect_sections,
    detect_transitions,
    extract_metrics,
    opener_distribution,
)


def test_metrics_average_sentence_and_paragraph() -> None:
    md = """# T

One sentence here. Second sentence.

Paragraph two. More words here.
"""
    m = extract_metrics(md)
    assert m.avg_sentence_words > 2
    assert m.avg_paragraph_sentences == 2


def test_bullets_do_not_inflate_word_count() -> None:
    md = """# T

Short paragraph.

- One
- Two words here
"""
    m = extract_metrics(md)
    assert m.avg_sentence_words < 10  # bullets excluded-ish


def test_paragraph_length_distribution() -> None:
    md = """# T

A. B. C.

D.
"""
    m = extract_metrics(md)
    assert m.paragraph_length_dist == [3, 1]


def test_transitions_deterministic_order() -> None:
    md = "# T\n\nHowever, one thing. Meanwhile another. But still."
    assert detect_transitions(md) == sorted(detect_transitions(md))
    assert set(detect_transitions(md)) >= {"however", "meanwhile", "but", "still"}


def test_sections_from_headings() -> None:
    md = "# A\n\nx\n\n## B\n\ny"
    assert detect_sections(md) == ["A", "B"]


def test_openers_detect_question() -> None:
    paragraphs = [["Why is it so?"], ["Meanwhile things changed."], ["It is fine."]]
    assert detect_openers(paragraphs) == ["question", "transition-opener", "declarative"]


def test_opener_distribution_counts_opener_types() -> None:
    md = "# T\n\nWhy is it so?\n\nMeanwhile things changed.\n\nIt is fine."
    assert opener_distribution(md) == {
        "question": 1,
        "transition-opener": 1,
        "declarative": 1,
    }


def test_numeric_density_counts_numbered_sentences() -> None:
    md = "# T\n\nWe hit 400M. A plain claim."
    m = extract_metrics(md)
    assert m.numeric_density == 0.5


def test_paragraph_ending_in_colon_still_counts() -> None:
    md = "# T\n\nThere are reasons, in reality:"

    dist = extract_metrics(md).paragraph_length_dist
    assert dist == [1]


def test_empty_or_heading_only_input_is_safe() -> None:
    assert extract_metrics("").paragraph_length_dist == []
    assert extract_metrics("# Just a heading").paragraph_length_dist == []
