"""Build the system prompt that asks the LLM to extract qualitative voice."""

from __future__ import annotations

import json

from factful.style.deterministic import detect_sections, detect_transitions, opener_distribution
from factful.style.schema import StyleExtraction, StyleMetrics

_EXTRACTION_INSTRUCTIONS = """
You are an expert editor analysing an author's writing style from their published
articles. Your job is to extract the QUALITATIVE voice dimensions only. The objective
numeric metrics (sentence length, paragraph length, numeric density) and structural
signals (section headings, transition words, paragraph opener types) are already
computed and supplied to you separately - do not recompute or contradict them.

GENERALISATION IS THE GOAL:
The profile must be a REUSABLE style guide. Every entry must apply to any article this
author writes, REGARDLESS OF TOPIC. Strip names, places, dates, events, and any
article-specific content. If an observation is about what the article is about rather
than how the author writes, discard it.

Rules:
- Copy EXACT verbatim excerpts from the samples. Never paraphrase, never summarize.
  Quoted excerpts are used as few-shot anchors for a writer.
- hook_patterns: SHORT, reusable labels (e.g. "declarative context", "rhetorical
  question", "direct address"). Never describe one specific article's opening.
- story_beats: STRUCTURAL, reusable moves (e.g. "opening context", "thesis",
  "bold-name profile lead", "contrast section", "future outlook", "one-line clincher").
  NEVER content summaries like "comparison of UAE and Iran" or "critique of military
  effectiveness". If a beat names a country, person, or event, it is topic-bound, not
  structural.
- transitions: reusable phrase-level connectives only (e.g. "on the other hand", "for
  example", "in reality", "while"). Omit clauses tied to one article (e.g. "as the war
  progresses").
- rhetorical_devices, direct_address, characterization: only report devices the author
  actually uses. The label is the ABSTRACT PATTERN (e.g. "rhetorical-question",
  "question-burst", "dear-reader", "hyperbolic-concrete"); the excerpt is one short
  verbatim snippet as a few-shot anchor. Only include a device if it RECURS: report
  count >= 2. Assess these fields deliberately - do not leave them empty when the
  author clearly uses the device.
- voice and tone: describe HOW the author sounds (e.g. "acerbic, skeptical,
  dry-humour"), never WHAT the author writes about. A voice tied to a topic (e.g.
  "geopolitical commentator") is not a style.
- opinion_hedges, comparatives, modals: reusable phrases/words, topic-neutral.
- numeric_style: how the author presents numbers (precision, rounding, units), not
  what the numbers say.
- Return structured JSON matching the supplied schema. Leave optional lists empty when
  a device is absent. Do not invent patterns that are not clearly present.
"""


def build_style_prompt(
    samples: list[str],
    metrics: StyleMetrics,
    name: str,
    schema_description: str,
) -> str:
    numbered = "\n\n".join(
        f"--- Sample {i + 1} ---\n{sample.strip()}" for i, sample in enumerate(samples)
    )
    return (
        f"Author/voice name: {name}\n\n"
        f"Computed numeric metrics:\n{metrics.model_dump_json(indent=2)}\n\n"
        f"Computed structural signals:\n{_structural_signals(samples)}\n\n"
        f"Sample articles:\n{numbered}\n\n"
        f"{_EXTRACTION_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n{schema_description}"
    )


def build_style_prompt_with_schema(
    samples: list[str],
    metrics: StyleMetrics,
    name: str,
    schema: type[StyleExtraction],
) -> str:
    return build_style_prompt(
        samples,
        metrics,
        name,
        json.dumps(schema.model_json_schema(), indent=2),
    )


def _structural_signals(samples: list[str]) -> str:
    combined = "\n\n".join(samples)
    return (
        f"section headings: {detect_sections(combined)}\n"
        f"transition words used: {detect_transitions(combined)}\n"
        f"paragraph opener types: {opener_distribution(combined)}"
    )
