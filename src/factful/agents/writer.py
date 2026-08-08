"""Writer agent: generate a fact-tagged Markdown draft in a given style."""

from __future__ import annotations

import json
import re

from factful.llm.client import ChatClient
from factful.schemas import Draft, SourceBundle
from factful.style.schema import StyleProfile

_CLAIM_TAG = re.compile(r"\[\[(?P<claim_id>\w+)\]\]")

_WRITER_INSTRUCTIONS = """
You are an expert Substack writer. Compose a COMPLETE Markdown article on the
topic below, in the exact voice and style of the supplied style profile.

Rule — factual grounding:
- Every factual sentence that uses a number, statistic, or sourced detail MUST end
  with an inline tag naming its source claim: [[claim_id]].
- Only use the claims in the source bundle. Never invent or guess any number that
  is not backed by a claim. A sentence without a claim tag must be pure opinion,
  framing, or transition.
- Include a short closing note listing the sources used.
- Match the profile's voice: hook style, sentence and paragraph length, tone,
  transitions, story beats, and CTA/sign-off where defined.

Compose the article now as Markdown that fits the supplied output schema.
"""


def build_writer_prompt(bundle: SourceBundle, profile: StyleProfile) -> str:
    citations = "\n\n".join(
        f"claim_id: {c.claim_id}\n"
        f"claim: {c.claim}\n"
        f"key_stat: {c.key_stat}\n"
        f"source_title: {c.source_title}\n"
        f"publisher: {c.publisher}\n"
        f"quote_snippet: {c.quote_snippet}"
        for c in bundle.citations
    )
    return (
        f"Topic: {bundle.topic}\n"
        f"Angle: {bundle.angle}\n\n"
        f"Style profile:\n{json.dumps(profile.model_dump(), indent=2)}\n\n"
        f"Source bundle (claims to ground the article):\n{citations}\n\n"
        f"{_WRITER_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(Draft.model_json_schema(), indent=2)}"
    )


def extract_referenced_claims(markdown: str) -> list[str]:
    claims: list[str] = []
    for match in _CLAIM_TAG.findall(markdown):
        if match not in claims:
            claims.append(match)
    return claims


def write_article(
    bundle: SourceBundle,
    profile: StyleProfile,
    *,
    client: ChatClient,
) -> Draft:
    prompt = build_writer_prompt(bundle, profile)
    result = client.chat_completion(prompt=prompt, schema=Draft)
    if not isinstance(result, Draft):
        raise TypeError(f"expected Draft, got {type(result).__name__}")
    return result
