from __future__ import annotations

import pytest
from pydantic import BaseModel

from factful.style.analyzer import (
    compute_confidence,
    extract_style,
    merge_profile,
    sanitize_extraction,
)
from factful.style.schema import DeviceExample, StyleExtraction, StyleMetrics, StyleProfile

METRICS = StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0)

EXTRACTION = StyleExtraction(
    voice="long-form, opinionated",
    tone="acerbic, skeptical",
    hook_patterns=["question", "direct-address"],
    story_beats=["Future Outlook", "bold-name profile lead"],
    transitions=["on the other hand", "while"],
    rhetorical_devices=[{"label": "rhetorical-question", "count": 5, "excerpt": "Why? Why not?"}],
    direct_address=[{"label": "dear-reader", "count": 3, "excerpt": "Dear reader, ..."}],
    characterization=[{"label": "sarcasm", "count": 4, "excerpt": "golden palaces"}],
    opinion_hedges=["I don't believe for a second", "I think"],
    comparatives=["more than any other", "second-largest"],
    modals=["probably", "seemingly"],
    numeric_style="400M$, hundreds of billions",
    cta_style=None,
    signoff_style=None,
)


def test_merge_profile_combines_metrics_and_extraction() -> None:
    profile = merge_profile("kevich", METRICS, EXTRACTION)
    assert isinstance(profile, StyleProfile)
    assert profile.name == "kevich"
    assert profile.metrics.avg_sentence_words == 16.0
    assert profile.extraction.tone == "acerbic, skeptical"
    assert profile.source_confidence == 1.0


def test_merge_profile_preserves_device_examples() -> None:
    profile = merge_profile("kevich", METRICS, EXTRACTION)
    assert profile.extraction.characterization[0].excerpt == "golden palaces"
    assert profile.extraction.direct_address[0].count == 3


class FakeClient:
    def __init__(self, result: BaseModel) -> None:
        self.result = result
        self.calls: list[tuple[str, type]] = []

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((prompt, schema))
        return self.result


def test_extract_style_with_fake_client() -> None:
    fake = FakeClient(EXTRACTION)
    profile = extract_style(["Sample body here. It is fine."], name="kevich", client=fake)
    assert profile.name == "kevich"
    assert profile.metrics.avg_sentence_words >= 3
    assert profile.extraction.tone == "acerbic, skeptical"
    assert fake.calls[0][1] is StyleExtraction
    assert "Sample body here" in fake.calls[0][0]


def test_extract_style_empty_samples_raises() -> None:
    fake = FakeClient(EXTRACTION)
    with pytest.raises(ValueError, match="at least one"):
        extract_style([], name="kevich", client=fake)


class ExplodingClient:
    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        raise RuntimeError("LLM down")


def test_extract_style_propagates_client_errors() -> None:
    with pytest.raises(RuntimeError, match="LLM down"):
        extract_style(["x"], name="kevich", client=ExplodingClient())


def test_sanitize_drops_topic_bound_story_beats() -> None:
    extraction = StyleExtraction(
        voice="cynical",
        tone="acerbic",
        story_beats=[
            "Ideological comparisons (UAE vs Iran)",
            "opening context",
            "Historical appeasement of the Emirates",
        ],
    )
    cleaned, dropped = sanitize_extraction(extraction)
    assert cleaned.story_beats == ["opening context"]
    assert dropped == 2


def test_sanitize_drops_topic_bound_hook_patterns() -> None:
    extraction = StyleExtraction(
        voice="cynical",
        tone="acerbic",
        hook_patterns=[
            "Contextualization of the Iran conflict",
            "rhetorical-question opener",
        ],
    )
    cleaned, dropped = sanitize_extraction(extraction)
    assert cleaned.hook_patterns == ["rhetorical-question opener"]
    assert dropped == 1


def test_sanitize_keeps_generic_transitions_and_beats() -> None:
    extraction = StyleExtraction(
        voice="long-form, opinionated",
        tone="acerbic, skeptical",
        story_beats=["opening context", "thesis", "bold-name profile leads"],
        transitions=["however", "but", "on the other hand"],
        hook_patterns=["declarative context", "rhetorical question"],
    )
    cleaned, dropped = sanitize_extraction(extraction)
    assert cleaned.story_beats == ["opening context", "thesis", "bold-name profile leads"]
    assert cleaned.transitions == ["however", "but", "on the other hand"]
    assert dropped == 0


def test_sanitize_drops_low_count_device_examples() -> None:
    extraction = StyleExtraction(
        voice="cynical",
        tone="acerbic",
        rhetorical_devices=[
            DeviceExample(label="rhetorical-question", count=1, excerpt="Why?"),
            DeviceExample(label="hyperbole", count=4, excerpt="golden palaces"),
        ],
    )
    cleaned, dropped = sanitize_extraction(extraction)
    assert [d.label for d in cleaned.rhetorical_devices] == ["hyperbole"]
    assert dropped == 0


def test_sanitize_drops_empty_and_duplicate_entries() -> None:
    extraction = StyleExtraction(
        voice="cynical",
        tone="acerbic",
        transitions=["however", "however", "", "but"],
        modals=["probably", "probably"],
    )
    cleaned, dropped = sanitize_extraction(extraction)
    assert cleaned.transitions == ["however", "but"]
    assert cleaned.modals == ["probably"]
    assert dropped == 0


def test_sanitize_preserves_valid_extraction_unchanged() -> None:
    cleaned, dropped = sanitize_extraction(EXTRACTION)
    assert dropped == 0
    assert cleaned.story_beats == ["Future Outlook", "bold-name profile lead"]


def test_compute_confidence_full_profile_is_one() -> None:
    assert compute_confidence(EXTRACTION, topic_leaks=0) == 1.0


def test_compute_confidence_penalizes_topic_leaks() -> None:
    assert compute_confidence(EXTRACTION, topic_leaks=2) < 1.0
    assert compute_confidence(EXTRACTION, topic_leaks=2) < compute_confidence(
        EXTRACTION, topic_leaks=0
    )


def test_compute_confidence_penalizes_empty_fields() -> None:
    sparse = StyleExtraction(
        voice="cynical",
        tone="acerbic",
        rhetorical_devices=[],
        direct_address=[],
        characterization=[],
        opinion_hedges=[],
        comparatives=[],
        modals=[],
        numeric_style="",
    )
    assert compute_confidence(sparse, topic_leaks=0) < 1.0
    assert compute_confidence(sparse, topic_leaks=0) < compute_confidence(EXTRACTION, topic_leaks=0)


def test_merge_profile_applies_sanitization_and_confidence() -> None:
    overfit = StyleExtraction(
        voice="Cynical geopolitical commentator",
        tone="Acerbic, derisive",
        story_beats=[
            "Ideological comparisons (UAE vs Iran)",
            "Historical appeasement of the Emirates",
        ],
    )
    profile = merge_profile("hanan", METRICS, overfit)
    assert profile.extraction.story_beats == []
    assert profile.source_confidence < 1.0


def test_merge_profile_preserves_high_quality_confidence() -> None:
    profile = merge_profile("kevich", METRICS, EXTRACTION)
    assert profile.source_confidence == 1.0
