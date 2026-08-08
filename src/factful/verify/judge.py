"""Attribution judge: closed-book claim-vs-passage verification."""

from __future__ import annotations

import json

from factful.llm.client import ChatClient
from factful.schemas import AttributionVerdict, Citation

_ATTRIBUTION_INSTRUCTIONS = """
You are an attribution judge. Your only job is to decide whether the specific
statistic in a claim is SUPPORTED by the retrieved passage from the cited source.

Rules:
- Base your answer ONLY on the passage shown here. Use no prior knowledge, no
  memory of other articles, no speculation.
- The passage is quoted verbatim from the source. Do not infer numbers that are
  not literally present.
- 'supported' only when the claim's specific number/stat is present in the passage.
  Everything else is 'unsupported'.
- Return structured JSON matching the supplied schema.
"""


def build_attribution_prompt(
    claim: str,
    key_stat: str,
    source_url: str,
    source_title: str,
    passage: str,
    passage_ref: str,
) -> str:
    return (
        f"Source URL: {source_url}\n"
        f"Source title: {source_title}\n"
        f"Passage ref: {passage_ref}\n\n"
        f"Claim: {claim}\n"
        f"Claim statistic: {key_stat}\n\n"
        f"Retrieved passage (verbatim):\n{passage}\n\n"
        f"{_ATTRIBUTION_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(AttributionVerdict.model_json_schema(), indent=2)}"
    )


def judge_claim(
    citation: Citation,
    passage: str,
    passage_ref: str,
    *,
    client: ChatClient,
) -> AttributionVerdict:
    prompt = build_attribution_prompt(
        claim=citation.claim,
        key_stat=citation.key_stat,
        source_url=citation.source_url,
        source_title=citation.source_title,
        passage=passage,
        passage_ref=passage_ref,
    )
    result = client.chat_completion(prompt=prompt, schema=AttributionVerdict)
    if not isinstance(result, AttributionVerdict):
        raise TypeError(f"expected AttributionVerdict, got {type(result).__name__}")
    return result
