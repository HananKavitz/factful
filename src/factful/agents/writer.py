"""Writer agent: generate a fact-tagged Markdown draft in a given style."""

from __future__ import annotations

import json
import re
from datetime import date

from factful.config import Settings
from factful.llm.client import ChatClient
from factful.schemas import CritiqueReport, Draft, FactVerdict, SourceBundle
from factful.style.schema import StyleProfile

_CLAIM_TAG = re.compile(r"\[\[(?P<claim_id>\w+)\]\]")


def _length_guidance(min_words: int, target_words: int, max_words: int) -> str:
    return (
        f"Length — aim for about {target_words} words, staying within "
        f"{min_words}-{max_words} words. Excessively long articles read as padded "
        f"and boring; trim ruthlessly."
    )


def _revision_length_guidance(min_words: int, target_words: int, max_words: int) -> str:
    return (
        f"Keep the article within {min_words}-{max_words} words (about {target_words}). "
        f"If feedback flags excessive length, trim toward the target without dropping "
        f"grounded claims."
    )


def _instructions_section(instructions: str | None) -> str:
    normalized = instructions.strip() if instructions else ""
    if not normalized:
        return ""
    return f"Writer instructions:\n{normalized}\n\n"


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
- Today's date is stated in the prompt. Treat that as the current date. Never imply
  that older data is current: when a statistic's source predates the current year,
  present it with its actual year (e.g. "as of 2023") rather than framing it as
  today's number.

Compose the article now as Markdown that fits the supplied output schema.
"""

_REVISION_INSTRUCTIONS = """
You are revising an existing Substack draft to address feedback. Apply TARGETED
edits only — do not rewrite the article from scratch.

Rules:
- Fix every issue listed by the critic and every fact-check revision suggestion.
- Do not alter sentences that were not flagged, except where a fix forces it.
- Keep the voice, structure, and style of the current draft; it already matches
  the style profile.
- Keep the [[claim_id]] tags exactly as they are. Never introduce a claim or
  number that is not in the source bundle.
- Do not drop sources unless the fact-checker flags a claim as unsupported and
  suggests removing it.

Return the revised article as Markdown that fits the supplied output schema.
"""


def build_writer_prompt(
    bundle: SourceBundle,
    profile: StyleProfile,
    *,
    settings: Settings | None = None,
    instructions: str | None = None,
    today: date | None = None,
) -> str:
    settings = settings if settings is not None else Settings()
    writer = settings.writer
    today = today or date.today()
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
        f"Today is {today.isoformat()}.\n\n"
        f"Style profile:\n{json.dumps(profile.model_dump(), indent=2)}\n\n"
        f"Source bundle (claims to ground the article):\n{citations}\n\n"
        f"{_instructions_section(instructions)}"
        f"{_WRITER_INSTRUCTIONS}\n\n"
        f"{_length_guidance(writer.min_words, writer.target_words, writer.max_words)}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(Draft.model_json_schema(), indent=2)}"
    )


def _render_feedback(verdicts: list[FactVerdict], critique: CritiqueReport) -> str:
    verdict_lines = "\n".join(
        f"- claim {v.claim_id} [{v.status}] confidence={v.confidence:.2f}: {v.reason}"
        + (f"\n  suggested_revision: {v.suggested_revision}" if v.suggested_revision else "")
        for v in verdicts
    )
    issue_lines = "\n".join(
        f"- [{i.severity}] {i.type}: {i.message}"
        + (f"\n  revision: {i.revision}" if i.revision else "")
        for i in critique.issues
    )
    return (
        f"Critic score: {critique.score}\n"
        f"Critic verdict: {critique.verdict}\n"
        f"Critic issues:\n{issue_lines or '- (none)'}\n\n"
        f"Fact-check verdicts:\n{verdict_lines or '- (none)'}"
    )


def build_revision_prompt(
    draft: Draft,
    verdicts: list[FactVerdict],
    critique: CritiqueReport,
    bundle: SourceBundle,
    profile: StyleProfile,
    *,
    settings: Settings | None = None,
    instructions: str | None = None,
    today: date | None = None,
) -> str:
    settings = settings if settings is not None else Settings()
    writer = settings.writer
    today = today or date.today()
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
        f"Today is {today.isoformat()}.\n\n"
        f"Style profile:\n{json.dumps(profile.model_dump(), indent=2)}\n\n"
        f"Source bundle (claims to ground the article):\n{citations}\n\n"
        f"Current draft:\n{draft.markdown}\n\n"
        f"Feedback to address:\n{_render_feedback(verdicts, critique)}\n\n"
        f"{_instructions_section(instructions)}"
        f"{_REVISION_INSTRUCTIONS}\n\n"
        f"{_revision_length_guidance(writer.min_words, writer.target_words, writer.max_words)}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(Draft.model_json_schema(), indent=2)}"
    )


def revise_article(
    draft: Draft,
    verdicts: list[FactVerdict],
    critique: CritiqueReport,
    bundle: SourceBundle,
    profile: StyleProfile,
    *,
    client: ChatClient,
    settings: Settings | None = None,
    instructions: str | None = None,
    today: date | None = None,
) -> Draft:
    prompt = build_revision_prompt(
        draft,
        verdicts,
        critique,
        bundle,
        profile,
        settings=settings,
        instructions=instructions,
        today=today,
    )
    result = client.chat_completion(prompt=prompt, schema=Draft)
    if not isinstance(result, Draft):
        raise TypeError(f"expected Draft, got {type(result).__name__}")
    return result


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
    settings: Settings | None = None,
    instructions: str | None = None,
    today: date | None = None,
) -> Draft:
    prompt = build_writer_prompt(
        bundle, profile, settings=settings, instructions=instructions, today=today
    )
    result = client.chat_completion(prompt=prompt, schema=Draft)
    if not isinstance(result, Draft):
        raise TypeError(f"expected Draft, got {type(result).__name__}")
    return result
