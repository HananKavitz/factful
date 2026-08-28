"""Pure functions for verifying image relevance to slide content."""

from __future__ import annotations

import re
from collections.abc import Sequence

# Common English stopwords to exclude from keyword matching
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "its",
        "it",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "how",
        "why",
        "when",
        "where",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "about",
        "into",
        "over",
        "after",
        "before",
        "between",
        "under",
        "above",
        "below",
        "up",
        "down",
        "out",
        "off",
        "than",
        "then",
        "also",
        "just",
        "very",
        "too",
        "here",
        "there",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "some",
        "any",
    }
)

# Rough list of common English nouns (non-exhaustive, for POS heuristics)
_COMMON_NOUNS: frozenset[str] = frozenset(
    {
        "time",
        "year",
        "people",
        "way",
        "day",
        "man",
        "woman",
        "child",
        "world",
        "life",
        "hand",
        "part",
        "place",
        "case",
        "week",
        "company",
        "system",
        "program",
        "question",
        "government",
        "number",
        "night",
        "point",
        "home",
        "water",
        "room",
        "mother",
        "area",
        "money",
        "story",
        "fact",
        "month",
        "lot",
        "right",
        "study",
        "book",
        "eye",
        "job",
        "word",
        "business",
        "issue",
        "side",
        "kind",
        "head",
        "house",
        "service",
        "friend",
        "father",
        "power",
        "hour",
        "game",
        "line",
        "end",
        "member",
        "city",
        "community",
        "name",
        "president",
        "team",
        "minute",
        "idea",
        "kid",
        "body",
        "information",
        "back",
        "parent",
        "face",
        "others",
        "level",
        "office",
        "door",
        "health",
        "person",
        "art",
        "war",
        "history",
        "party",
        "result",
        "change",
        "morning",
        "reason",
        "research",
        "girl",
        "guy",
        "moment",
        "air",
        "teacher",
        "force",
        "education",
    }
)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercased words, stripping punctuation."""
    cleaned = re.sub(r"[^a-z0-9' ]", "", text.lower())
    return [w for w in cleaned.split() if w and w not in _STOPWORDS]


def _extract_nouns(text: str) -> set[str]:
    """Heuristically extract likely nouns from text.

    Returns words that are capitalized or camelCase (proper nouns),
    or in a known common-noun list. No external POS tagger dependency.
    """
    tokens = text.split()
    nouns: set[str] = set()
    for token in tokens:
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", token)
        if not cleaned:
            continue
        # Proper nouns: start with uppercase OR have mixed case (e.g. iPhone)
        if cleaned[0].isupper() or (len(cleaned) > 1 and any(c.isupper() for c in cleaned[1:])):
            nouns.add(cleaned.lower())
        # Common nouns in our known list
        elif cleaned.lower() in _COMMON_NOUNS:
            nouns.add(cleaned.lower())
    return nouns


def keyword_overlap(heading: str, image_tags: Sequence[str], threshold: float = 0.3) -> bool:
    """Return True if at least *threshold* of heading keywords appear in image_tags.

    Args:
        heading: The slide heading text.
        image_tags: Tags or keywords associated with the image.
        threshold: Minimum proportion of heading tokens that must match.

    Returns:
        True if the image is sufficiently relevant to the heading.
    """
    heading_tokens = set(_tokenize(heading))
    if not heading_tokens:
        return True  # nothing to compare — pass
    if not image_tags:
        return True  # no tags to compare — can't judge relevance, pass
    tag_set = set(t.lower() for t in image_tags)
    overlap = heading_tokens & tag_set
    return len(overlap) / len(heading_tokens) >= threshold


def noun_jaccard(heading: str, alt_description: str | None, threshold: float = 0.15) -> bool:
    """Return True if noun-level Jaccard similarity meets the threshold.

    Extracts nouns from both the heading and the alt description,
    then computes |intersection| / |union|.

    Args:
        heading: The slide heading text.
        alt_description: The image's alt text or description (may be None).
        threshold: Minimum Jaccard score.

    Returns:
        True if similarity meets or exceeds the threshold.
    """
    heading_nouns = _extract_nouns(heading)
    if not heading_nouns:
        return True  # heading has no extractable nouns — pass
    if not alt_description:
        return True  # no description to compare — pass
    desc_nouns = _extract_nouns(alt_description)
    if not desc_nouns:
        return False  # description has no nouns but heading does — fail
    union = heading_nouns | desc_nouns
    intersection = heading_nouns & desc_nouns
    return len(intersection) / len(union) >= threshold
