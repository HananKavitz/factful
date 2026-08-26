"""URL extraction from free-text prompts (e.g. topic, instructions)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+")


def extract_urls(text: str) -> list[str]:
    """Return deduplicated HTTP(S) URLs found in *text*.

    Bare ``www.``-prefixed strings are promoted to ``https://`` URLs.
    URLs without a parseable hostname containing at least one dot are
    rejected.  Order of first occurrence is preserved.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for match in _URL_RE.finditer(text):
        raw = match.group(0)

        # Strip trailing punctuation that the broad regex may have captured:
        # comma, period, closing paren, closing bracket, closing brace,
        # semicolon, colon, exclamation, question mark, single/double quote.
        raw = raw.rstrip(".,);:!?\"'")

        if raw.startswith("www."):
            raw = "https://" + raw

        parts = urlsplit(raw)
        host = parts.hostname or ""
        if "." not in host:
            continue

        if raw not in seen:
            seen.add(raw)
            urls.append(raw)

    return urls
