"""Build the system prompt that asks the LLM to extract qualitative voice."""

from __future__ import annotations

import json

from factful.style.schema import StyleExtraction, StyleMetrics

_EXTRACTION_INSTRUCTIONS = """
You are an expert editor analysing an author's writing style from their published
articles. Your job is to extract the QUALITATIVE voice dimensions only. The objective
numeric metrics (sentence length, paragraph length, numeric density) are already
computed and supplied to you separately - do not recompute or contradict them.

Rules:
- Copy EXACT verbatim excerpts from the samples. Never paraphrase, never summarize.
  Quoted excerpts are used as few-shot anchors for a writer.
- For characterisation and rhetorical devices, capture the author's most distinctive,
  recognisable turns of phrase (jokes, insults, metaphors, hyperbole, direct address).
- Identify the tone accurately (e.g. acerbic, skeptical, derisive, dry humour) - do not
  flatten it to a generic label.
- Story beats: list the article's section structure in order, including bold-name
  paragraph leads (e.g. a section led by **Person Name**), not just ## headings.
- Transitions: phrase-level connectives the author favours (e.g. "on the other hand",
  "for example", "in reality", "while").
- Modals/hedges: words like "probably", "seemingly", "perhaps", "might", "could",
  plus hypothetical markers ("what if", "imagine").
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
