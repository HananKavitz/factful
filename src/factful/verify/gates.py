"""Deterministic numeric and date sanity gates for a citation."""

from __future__ import annotations

from datetime import date, datetime

from factful.verify.corroborate import extract_numbers


def parse_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def numeric_gates(
    claim: str,
    key_stat: str,
    quote_snippet: str,
    publish_date: str,
    max_currency_years: float = 2.0,
    *,
    today: date | None = None,
) -> list[str]:
    flags: list[str] = []

    key_values = extract_numbers(key_stat)
    if key_values and "%" in key_stat:
        too_high = max(key_values) > 100.0
        if too_high:
            flags.append(f"implausible percentage: {key_stat}")

    if "%" in key_stat:
        quote_has_percent = "%" in quote_snippet or "percent" in quote_snippet.lower()
        if quote_has_percent:
            quote_percents = extract_numbers(quote_snippet)
            if len(quote_percents) >= 2 and key_values and max(quote_percents) != key_values[0]:
                flags.append("possible percent-point vs percent-change confusion")

    published = parse_date(publish_date)
    if published is not None:
        reference = today or date.today()
        if (reference - published).days > max_currency_years * 365:
            flags.append(
                f"source dated {published.isoformat()} is over {max_currency_years} years old"
            )

    return flags
