"""Orchestrate deterministic metrics + LLM extraction into a StyleProfile."""

from __future__ import annotations

import re

from factful.llm.client import ChatClient
from factful.style.deterministic import extract_metrics
from factful.style.prompt import build_style_prompt_with_schema
from factful.style.schema import DeviceExample, StyleExtraction, StyleMetrics, StyleProfile

_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_CAPITALIZED_RE = re.compile(r"\b[A-Z][a-z]+\b")

_GENERIC_CAPS = frozenset(
    {
        "East",
        "Future",
        "Middle",
        "Outlook",
        "West",
        "World",
    }
)


def _is_topic_bound(entry: str) -> bool:
    if _ACRONYM_RE.search(entry):
        return True
    tokens = entry.split()
    for token in tokens[1:]:
        if _CAPITALIZED_RE.fullmatch(token) and token not in _GENERIC_CAPS:
            return True
    return False


def sanitize_extraction(extraction: StyleExtraction) -> tuple[StyleExtraction, int]:
    topic_leaks = 0

    def clean_strings(items: list[str]) -> list[str]:
        nonlocal topic_leaks
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in items:
            entry = item.strip()
            if not entry:
                continue
            key = entry.lower()
            if key in seen:
                continue
            if _is_topic_bound(entry):
                topic_leaks += 1
                continue
            seen.add(key)
            cleaned.append(entry)
        return cleaned

    def clean_devices(items: list[DeviceExample]) -> list[DeviceExample]:
        return [device for device in items if device.count >= 2]

    cleaned = extraction.model_copy(
        update={
            "hook_patterns": clean_strings(extraction.hook_patterns),
            "story_beats": clean_strings(extraction.story_beats),
            "transitions": clean_strings(extraction.transitions),
            "rhetorical_devices": clean_devices(extraction.rhetorical_devices),
            "direct_address": clean_devices(extraction.direct_address),
            "characterization": clean_devices(extraction.characterization),
            "opinion_hedges": clean_strings(extraction.opinion_hedges),
            "comparatives": clean_strings(extraction.comparatives),
            "modals": clean_strings(extraction.modals),
        }
    )
    return cleaned, topic_leaks


def compute_confidence(extraction: StyleExtraction, *, topic_leaks: int) -> float:
    qualitative = [
        extraction.voice,
        extraction.tone,
        extraction.hook_patterns,
        extraction.story_beats,
        extraction.transitions,
        extraction.rhetorical_devices,
        extraction.direct_address,
        extraction.characterization,
        extraction.opinion_hedges,
        extraction.comparatives,
        extraction.modals,
        extraction.numeric_style,
    ]
    empty = sum(1 for field in qualitative if not field)
    score = 1.0 - 0.1 * topic_leaks - 0.05 * empty
    return round(min(1.0, max(0.0, score)), 2)


def merge_profile(
    name: str,
    metrics: StyleMetrics,
    extraction: StyleExtraction,
) -> StyleProfile:
    cleaned, topic_leaks = sanitize_extraction(extraction)
    return StyleProfile(
        name=name,
        metrics=metrics,
        extraction=cleaned,
        source_confidence=compute_confidence(cleaned, topic_leaks=topic_leaks),
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
