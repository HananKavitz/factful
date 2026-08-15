"""Critic agent: reader-engagement review and revision feedback."""

from __future__ import annotations

import json
import re

from factful.config import Settings
from factful.llm.client import ChatClient
from factful.schemas import CritiqueReport, Draft, Issue

_CLAIM_TAG_RE = re.compile(r"\[\[(?P<claim_id>\w+)\]\]")

_CRITIC_INSTRUCTIONS = """
You are a demanding reader-focused editor. Review the Markdown article and score
how well it would hold a Substack reader.

Evaluate:
- Hook: does the opener pull a scrolling reader in?
- Readability: sentence and paragraph length, flow (the supplied reading grade is
  computed deterministically; treat it as authoritative).
- Length: the supplied word count is computed deterministically; treat it as
  authoritative. Heavily penalize drafts that exceed the word-count ceiling —
  excessive length reads as padding and kills engagement. Flag it as an issue with
  a concrete trimming revision (cut padding, merge redundant sentences, tighten
  transitions). Note without heavy penalty when a draft falls well below the floor
  and feels thin.
- Argument structure: every claim follows claim -> evidence -> implication.
- Macro-structure: grounded facts are presented first as a coherent state-of-play
  block; interpretation and opinion follow; any recommended action plan comes
  last, before the closer. Penalize scattered facts (claims interleaved with
  opinion throughout), late-arriving statistics, and a closer that carries a
  claim tag. For each structure weakness list a concrete restructure revision.
- Calls to action and sign-off.

Score 0-100. For each material weakness, list an issue with a concrete revision
suggestion. Verdict is 'pass' when the score reaches the bar, else 'rework'.
Return structured JSON matching the supplied schema.
"""


def reading_grade(text: str) -> float:
    """Flesch reading-ease for a prose block; higher is easier."""
    sentences = max(1, len(re.findall(r"[.!?](?:\s|$)", text)) or 1)
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    syllables = sum(max(1, _syllables(w)) for w in re.findall(r"[A-Za-z]+", text))
    if words == 0:
        return 0.0
    return 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)


def word_count(text: str) -> int:
    """Deterministic word count (matches the reading-grade tokenizer)."""
    return len(re.findall(r"[A-Za-z0-9]+", text))


def enforce_length_feedback(
    report: CritiqueReport,
    *,
    words: int,
    min_words: int,
    max_words: int,
) -> CritiqueReport:
    """Replace the LLM's length feedback with a deterministic one when out of bounds."""
    if min_words <= words <= max_words:
        return report
    if words < min_words:
        message = (
            f"Deterministic word count {words} is below the minimum of {min_words}. "
            f"The draft is too thin; it must be expanded before it can be published."
        )
        revision = (
            f"Expand the article to at least {min_words} words: develop each grounded "
            f"claim with more evidence, implications, and transitions, and deepen the "
            f"argument without adding unsourced filler."
        )
    else:
        message = (
            f"Deterministic word count {words} exceeds the maximum of {max_words}. "
            f"The draft is too long; it must be trimmed before it can be published."
        )
        revision = (
            f"Cut at least {words - max_words} words: remove padding, merge redundant "
            f"sentences, and tighten transitions."
        )
    issues = [issue for issue in report.issues if issue.type.lower() != "length"]
    issues.append(Issue(type="Length", severity="high", message=message, revision=revision))
    return report.model_copy(update={"issues": issues})


def enforce_structure_feedback(report: CritiqueReport, *, markdown: str) -> CritiqueReport:
    """Replace the LLM's structure feedback with a deterministic one when the
    draft's claim placement violates the facts-first, plan-last contract."""
    paragraphs = [p for p in re.split(r"\n\s*\n", markdown.strip()) if p.strip()]
    count = len(paragraphs)
    if count < 4:
        return report
    claim_paragraphs = [i for i, p in enumerate(paragraphs) if _CLAIM_TAG_RE.search(p)]
    if not claim_paragraphs:
        return report

    issues: list[Issue] = []
    if _CLAIM_TAG_RE.search(paragraphs[-1]):
        issues.append(
            Issue(
                type="Structure",
                severity="high",
                message=(
                    "The final paragraph (the closer) carries a grounded claim. "
                    "The closing line must be pure rhetoric, not a statistic."
                ),
                revision=(
                    "Move that statistic into the state-of-play block near the start "
                    "of the article and close with a rhetorical line carrying no claim tag."
                ),
            )
        )

    quarter_start = int(0.75 * count)
    late = [i for i in claim_paragraphs if i >= quarter_start]
    if late and len(late) / len(claim_paragraphs) > 0.25:
        issues.append(
            Issue(
                type="Structure",
                severity="high",
                message=(
                    "Grounded facts appear late in the article, scattered through "
                    "the argument, instead of leading it."
                ),
                revision=(
                    "Consolidate every grounded claim into a single state-of-play "
                    "block at the start; keep the diagnosis and action plan free of "
                    "new statistics."
                ),
            )
        )

    if claim_paragraphs[0] > int(0.3 * count):
        issues.append(
            Issue(
                type="Structure",
                severity="moderate",
                message=(
                    "The article opens with several paragraphs of opinion before "
                    "presenting any grounded fact."
                ),
                revision=(
                    "Lead with the facts: open the state-of-play block early so "
                    "readers see the evidence before the argument."
                ),
            )
        )

    if not issues:
        return report
    kept = [issue for issue in report.issues if issue.type.lower() != "structure"]
    return report.model_copy(update={"issues": kept + issues})


def _syllables(word: str) -> int:
    count = len(re.findall(r"[aeiouy]+", word.lower()))
    return count


def build_critic_prompt(
    draft: Draft,
    grade: float,
    *,
    words: int,
    min_words: int,
    max_words: int,
) -> str:
    return (
        f"Article draft:\n{draft.markdown}\n\n"
        f"Deterministic reading grade (Flesch reading-ease, higher is easier): {grade:.1f}\n"
        f"Deterministic word count: {words} words (target range {min_words}-{max_words})\n\n"
        f"{_CRITIC_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(CritiqueReport.model_json_schema(), indent=2)}"
    )


def critique(
    draft: Draft,
    *,
    client: ChatClient,
    settings: Settings | None = None,
) -> CritiqueReport:
    settings = settings if settings is not None else Settings()
    grade = reading_grade(draft.markdown)
    words = word_count(draft.markdown)
    prompt = build_critic_prompt(
        draft,
        grade,
        words=words,
        min_words=settings.writer.min_words,
        max_words=settings.writer.max_words,
    )
    result = client.chat_completion(prompt=prompt, schema=CritiqueReport)
    if not isinstance(result, CritiqueReport):
        raise TypeError(f"expected CritiqueReport, got {type(result).__name__}")
    report = enforce_structure_feedback(result, markdown=draft.markdown)
    return enforce_length_feedback(
        report,
        words=words,
        min_words=settings.writer.min_words,
        max_words=settings.writer.max_words,
    )
