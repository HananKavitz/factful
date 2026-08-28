"""Tests for the slide parser."""

from __future__ import annotations

from factful.video.slides import Slide, parse_slides


def test_empty_markdown_returns_empty_list() -> None:
    assert parse_slides("") == []
    assert parse_slides("   ") == []
    assert parse_slides("\n\n\n") == []


def test_no_headings_wraps_as_single_slide() -> None:
    body = "Just a paragraph.\n\nAnother paragraph."
    result = parse_slides(body, title="My Title")
    assert len(result) == 1
    assert result[0].heading == "My Title"
    assert result[0].body_lines == ["Just a paragraph.", "Another paragraph."]


def test_no_headings_without_title_uses_fallback() -> None:
    body = "Just text."
    result = parse_slides(body)
    assert len(result) == 1
    assert result[0].heading == "Article"


def test_splits_on_h1_headings() -> None:
    md = "# Introduction\n\nOpening text.\n\n# Deep Dive\n\nDetails here."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Introduction"
    assert result[0].body_lines == ["Opening text."]
    assert result[1].heading == "Deep Dive"
    assert result[1].body_lines == ["Details here."]


def test_splits_on_mixed_heading_levels() -> None:
    md = "# Title\n\nLead.\n\n## Section\n\nBody text."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Title"
    assert result[0].body_lines == ["Lead."]
    assert result[1].heading == "Section"
    assert result[1].body_lines == ["Body text."]


def test_heading_without_body_is_empty_slide() -> None:
    md = "# Only Heading\n\n## Next Section\n\nHas body."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Only Heading"
    assert result[0].body_lines == []
    assert result[1].heading == "Next Section"
    assert result[1].body_lines == ["Has body."]


def test_heading_with_only_blank_lines_is_empty() -> None:
    md = "# Heading\n\n   \n\n## Next\n\nBody."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Heading"
    assert result[0].body_lines == []
    assert result[1].heading == "Next"
    assert result[1].body_lines == ["Body."]


def test_preserves_multiple_paragraphs_under_one_heading() -> None:
    md = "# Section\n\nFirst para.\n\nSecond para.\n\nThird para."
    result = parse_slides(md)
    assert len(result) == 1
    assert result[0].heading == "Section"
    assert result[0].body_lines == ["First para.", "Second para.", "Third para."]


def test_text_before_first_heading_becomes_intro_slide() -> None:
    md = "This is an intro paragraph without a heading.\n\n# First Section\n\nBody text."
    result = parse_slides(md, title="My Story")
    assert len(result) == 2
    assert result[0].heading == "My Story"
    assert result[0].body_lines == ["This is an intro paragraph without a heading."]
    assert result[1].heading == "First Section"
    assert result[1].body_lines == ["Body text."]


def test_intro_slide_uses_title_fallback_without_title() -> None:
    md = "Intro text.\n\n# Section\n\nBody."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Introduction"
    assert result[0].body_lines == ["Intro text."]
    assert result[1].heading == "Section"


def test_only_whitespace_before_first_heading_does_not_create_intro() -> None:
    md = "   \n\n# Section\n\nBody."
    result = parse_slides(md, title="Title")
    assert len(result) == 1
    assert result[0].heading == "Section"


def test_slide_structure_is_dataclass() -> None:
    slide = Slide(heading="Test", body_lines=["a", "b"])
    assert slide.heading == "Test"
    assert slide.body_lines == ["a", "b"]


def test_slide_default_body_lines_is_empty() -> None:
    slide = Slide(heading="Test")
    assert slide.body_lines == []


def test_triple_hash_heading() -> None:
    md = "### Subsection\n\nContent.\n\n# Major\n\nStuff."
    result = parse_slides(md)
    assert len(result) == 2
    assert result[0].heading == "Subsection"
    assert result[0].body_lines == ["Content."]
    assert result[1].heading == "Major"
    assert result[1].body_lines == ["Stuff."]
