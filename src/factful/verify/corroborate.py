"""Bundle-scoped corroboration: deterministic normalization of key stats."""

from __future__ import annotations

import re

from factful.schemas import Citation

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PERCENT_WORDS = {"%", "percent", "pct"}
_MAGNITUDES = {
    "k": "thousand",
    "thousand": "thousand",
    "m": "million",
    "million": "million",
    "b": "billion",
    "bn": "billion",
    "billion": "billion",
    "t": "trillion",
    "trillion": "trillion",
}


def extract_numbers(text: str) -> list[float]:
    return [float(match.replace(",", "")) for match in _NUMBER.findall(text)]


def normalize_key_stat(key_stat: str) -> tuple[float, str] | None:
    numbers = extract_numbers(key_stat)
    if not numbers:
        return None
    value = numbers[0]
    unit = _NUMBER.sub("", key_stat).strip().lower().replace(",", "")
    if unit in _PERCENT_WORDS:
        return value, "%"
    unit = unit.lstrip("$").strip()
    if unit in _MAGNITUDES:
        return value, _MAGNITUDES[unit]
    if len(unit) == 1 and unit in _MAGNITUDES:
        return value, _MAGNITUDES[unit]
    return value, unit


def _independent_others(citations: list[Citation], claim: Citation) -> list[Citation]:
    seen: set[str] = set()
    others: list[Citation] = []
    for other in citations:
        if other.claim_id == claim.claim_id or other.source_url == claim.source_url:
            continue
        if other.source_url in seen:
            continue
        seen.add(other.source_url)
        others.append(other)
    return others


def corroborating_sources(citations: list[Citation], claim: Citation) -> list[str]:
    target = normalize_key_stat(claim.key_stat)
    if target is None:
        return []
    return [
        other.source_url
        for other in _independent_others(citations, claim)
        if normalize_key_stat(other.key_stat) == target
    ]


def contradicting_sources(citations: list[Citation], claim: Citation) -> list[str]:
    target = normalize_key_stat(claim.key_stat)
    if target is None:
        return []
    value, unit = target

    def conflicts(other: Citation) -> bool:
        normalized = normalize_key_stat(other.key_stat)
        if normalized is None:
            return False
        other_value, other_unit = normalized
        return other_unit == unit and other_value != value

    return [other.source_url for other in _independent_others(citations, claim) if conflicts(other)]
