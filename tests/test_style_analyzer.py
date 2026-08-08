from __future__ import annotations

import pytest
from pydantic import BaseModel

from factful.style.analyzer import extract_style, merge_profile
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile

METRICS = StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0)

EXTRACTION = StyleExtraction(
    voice="long-form, opinionated",
    tone="acerbic, skeptical",
    hook_patterns=["question", "direct-address"],
    story_beats=["Future Outlook", "**Nasser** lead"],
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
