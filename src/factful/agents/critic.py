"""Critic agent: reader-engagement review and revision feedback."""

from __future__ import annotations

import json
import re

from factful.llm.client import ChatClient
from factful.schemas import CritiqueReport, Draft

_CRITIC_INSTRUCTIONS = """
You are a demanding reader-focused editor. Review the Markdown article and score
how well it would hold a Substack reader.

Evaluate:
- Hook: does the opener pull a scrolling reader in?
- Readability: sentence and paragraph length, flow (the supplied reading grade is
  computed deterministically; treat it as authoritative).
- Argument structure: every claim follows claim -> evidence -> implication.
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


def _syllables(word: str) -> int:
    count = len(re.findall(r"[aeiouy]+", word.lower()))
    return count


def build_critic_prompt(draft: Draft, grade: float) -> str:
    return (
        f"Article draft:\n{draft.markdown}\n\n"
        f"Deterministic reading grade (Flesch reading-ease, higher is easier): {grade:.1f}\n\n"
        f"{_CRITIC_INSTRUCTIONS}\n\n"
        f"Output schema (return JSON matching this shape):\n"
        f"{json.dumps(CritiqueReport.model_json_schema(), indent=2)}"
    )


def critique(draft: Draft, *, client: ChatClient) -> CritiqueReport:
    grade = reading_grade(draft.markdown)
    prompt = build_critic_prompt(draft, grade)
    result = client.chat_completion(prompt=prompt, schema=CritiqueReport)
    if not isinstance(result, CritiqueReport):
        raise TypeError(f"expected CritiqueReport, got {type(result).__name__}")
    return result
