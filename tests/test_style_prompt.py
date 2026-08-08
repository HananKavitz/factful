from __future__ import annotations

from factful.style.prompt import build_style_prompt_with_schema
from factful.style.schema import StyleExtraction, StyleMetrics

METRICS = StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0)


def test_prompt_embeds_samples() -> None:
    prompt = build_style_prompt_with_schema(
        ["Sample one body", "Sample two body"], METRICS, "kevich", StyleExtraction
    )
    assert "Sample one body" in prompt
    assert "Sample two body" in prompt
    assert "kevich" in prompt


def test_prompt_embeds_metrics() -> None:
    prompt = build_style_prompt_with_schema(["x"], METRICS, "kevich", StyleExtraction)
    assert "avg_sentence_words" in prompt
    assert "16.0" in prompt


def test_prompt_forbids_summarizing() -> None:
    prompt = build_style_prompt_with_schema(["x"], METRICS, "kevich", StyleExtraction)
    lowered = prompt.lower()
    assert "verbatim" in lowered
    assert "never summarize" in lowered


def test_prompt_requires_schema() -> None:
    prompt = build_style_prompt_with_schema(["x"], METRICS, "kevich", StyleExtraction)
    assert '"voice"' in prompt
    assert '"tone"' in prompt


def test_prompt_numbered_samples() -> None:
    prompt = build_style_prompt_with_schema(["a", "b"], METRICS, "kevich", StyleExtraction)
    assert "Sample 1" in prompt
    assert "Sample 2" in prompt
