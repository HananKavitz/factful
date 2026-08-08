"""Deterministic, pure-Python style metrics. No LLM, no I/O."""

from __future__ import annotations

import re

from factful.style.schema import StyleMetrics

HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+(?=\s|\Z)|$)")
BULLET_RE = re.compile(r"^\s*[-*]\s+")

TRANSITION_WORDS = (
    "however",
    "so",
    "therefore",
    "meanwhile",
    "moreover",
    "furthermore",
    "then",
    "but",
    "yet",
    "still",
    "thus",
    "hence",
)

HOOK_TRANSITIONS = {"however", "but", "yet", "so", "and", "meanwhile"}
NUMBER_RE = re.compile(r"\d")


def _split_sentences(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    sentences = [s.strip() for s in SENTENCE_RE.findall(raw)]
    sentences = [s for s in sentences if s]
    return sentences


def _split_paragraphs(text: str) -> list[list[str]]:
    blocks = re.split(r"\n\s*\n", text.strip())
    return [_split_sentences(block) for block in blocks if block.strip()]


def _word_count(sentence: str) -> int:
    stripped = BULLET_RE.sub("", sentence.strip())
    return len(stripped.split())


def _mean(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def extract_metrics(markdown: str) -> StyleMetrics:
    body = "\n".join(line for line in markdown.splitlines() if not HEADING_RE.match(line))
    paragraphs = _split_paragraphs(body)
    sentences = [s for block in paragraphs for s in block]
    word_counts = [_word_count(s) for s in sentences]

    paragraph_length_dist = [len(block) for block in paragraphs]

    total_numeric_tokens = sum(1 for s in sentences if NUMBER_RE.search(s))
    numeric_density = round(total_numeric_tokens / len(sentences), 3) if sentences else 0.0

    return StyleMetrics(
        avg_sentence_words=_mean(word_counts),
        avg_paragraph_sentences=_mean(paragraph_length_dist),
        paragraph_length_dist=paragraph_length_dist,
        numeric_density=numeric_density,
    )


def detect_sections(markdown: str) -> list[str]:
    return [
        match.group(1).strip()
        for line in markdown.splitlines()
        if (match := HEADING_RE.match(line))
    ]


def detect_transitions(markdown: str) -> list[str]:
    lowered = markdown.lower()
    return sorted(word for word in TRANSITION_WORDS if re.search(rf"\b{word}\b", lowered))


def detect_openers(paragraphs: list[list[str]]) -> list[str]:
    hooks: list[str] = []
    for block in paragraphs:
        if not block:
            continue
        opener = block[0].lower().strip()
        if opener.endswith("?"):
            hooks.append("question")
        else:
            first = re.sub(r"\W", "", opener.split(" ", 1)[0])
            if first in HOOK_TRANSITIONS:
                hooks.append("transition-opener")
            else:
                hooks.append("declarative")
    return hooks
