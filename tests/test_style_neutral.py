from __future__ import annotations

from factful.style.neutral import neutral_profile
from factful.style.schema import StyleProfile


def test_neutral_profile_is_a_valid_style_profile() -> None:
    profile = neutral_profile()
    assert isinstance(profile, StyleProfile)
    assert profile.name == "neutral"
    assert profile.source_confidence == 0.0


def test_neutral_profile_imposes_no_voice() -> None:
    profile = neutral_profile()
    assert profile.extraction.voice == ""
    assert profile.extraction.tone == ""
    assert profile.extraction.hook_patterns == []
    assert profile.extraction.story_beats == []


def test_neutral_profile_has_sane_paragraph_metrics() -> None:
    profile = neutral_profile()
    assert profile.metrics.avg_paragraph_sentences == 3.0
    assert profile.metrics.paragraph_length_dist == [3]


def test_neutral_profile_allows_custom_name() -> None:
    assert neutral_profile(name="new-user").name == "new-user"
