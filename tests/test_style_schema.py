from __future__ import annotations

import pytest
from pydantic import ValidationError

from factful.style.schema import DeviceExample, StyleExtraction, StyleMetrics, StyleProfile


def test_metrics_defaults() -> None:
    m = StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0)
    assert m.paragraph_length_dist == []
    assert m.numeric_density == 0.0


def test_device_example_enforces_non_negative_count() -> None:
    with pytest.raises(ValidationError):
        DeviceExample(label="sarcasm", count=-1)


def test_profile_extra_forbid_rejects_unknown_field() -> None:
    profile = StyleProfile(
        name="x",
        metrics=StyleMetrics(avg_sentence_words=1.0, avg_paragraph_sentences=1.0),
        extraction=StyleExtraction(voice="v", tone="t"),
    )
    with pytest.raises(ValidationError):
        profile.model_dump()
        StyleProfile.model_validate(profile.model_dump() | {"bogus": 1})


def test_device_example_defaults() -> None:
    d = DeviceExample(label="rhetorical-question")
    assert d.count == 0
    assert d.excerpt == ""


def test_source_confidence_bounded() -> None:
    with pytest.raises(ValidationError):
        StyleProfile(
            name="x",
            metrics=StyleMetrics(avg_sentence_words=1.0, avg_paragraph_sentences=1.0),
            extraction=StyleExtraction(voice="v", tone="t"),
            source_confidence=5.0,
        )
