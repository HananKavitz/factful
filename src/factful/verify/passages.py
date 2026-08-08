"""Deterministic passage extraction for verification retrieval."""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"\s+")


def split_passages(text: str) -> list[str]:
    """Split source text into non-empty sentence passages."""
    passages: list[str] = []
    for chunk in _SENTENCE_SPLIT.split(text):
        sentence = _WHITESPACE.sub(" ", chunk).strip()
        if sentence:
            passages.append(sentence)
    return passages
