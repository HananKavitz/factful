"""Orchestrate deterministic metrics + LLM extraction into a StyleProfile."""

from __future__ import annotations

from factful.llm.client import ChatClient
from factful.style.deterministic import extract_metrics
from factful.style.prompt import build_style_prompt_with_schema
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile


def merge_profile(
    name: str,
    metrics: StyleMetrics,
    extraction: StyleExtraction,
) -> StyleProfile:
    return StyleProfile(
        name=name,
        metrics=metrics,
        extraction=extraction,
        source_confidence=1.0,
    )


def extract_style(
    samples: list[str],
    name: str,
    *,
    client: ChatClient,
) -> StyleProfile:
    if not samples:
        raise ValueError("at least one sample article is required")
    metrics = extract_metrics("\n\n".join(samples))
    prompt = build_style_prompt_with_schema(samples, metrics, name, StyleExtraction)
    extraction = client.chat_completion(prompt=prompt, schema=StyleExtraction)
    if not isinstance(extraction, StyleExtraction):
        raise TypeError(f"expected StyleExtraction, got {type(extraction).__name__}")
    return merge_profile(name, metrics, extraction)
