"""A neutral StyleProfile used when a user has not set their own writing style."""

from __future__ import annotations

from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile


def neutral_profile(name: str = "neutral") -> StyleProfile:
    return StyleProfile(
        name=name,
        metrics=StyleMetrics(
            avg_sentence_words=18.0,
            avg_paragraph_sentences=3.0,
            paragraph_length_dist=[3],
            numeric_density=0.0,
        ),
        extraction=StyleExtraction(voice="", tone=""),
        source_confidence=0.0,
    )
