"""Parse markdown into a slide deck for video rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


@dataclass
class Slide:
    """A single slide in the video, derived from a markdown heading section."""

    heading: str
    body_lines: list[str] = field(default_factory=list)


def parse_slides(markdown: str, title: str = "") -> list[Slide]:
    """Split markdown into slides based on headings.

    Each ``#``, ``##``, or ``###`` heading starts a new slide. The body
    under that heading (until the next heading) becomes the slide's body lines.

    Any text that appears *before* the first heading is treated as an intro
    slide with the story *title* as its heading.

    If the markdown has no headings at all, the entire body is returned as a
    single slide using *title* as the heading.

    Args:
        markdown: The article text.
        title: Fallback heading when no headings are found.

    Returns:
        A list of Slide dataclass instances, preserving document order.
    """
    if not markdown or not markdown.strip():
        return []

    headings = list(_HEADING_RE.finditer(markdown))

    if not headings:
        # No headings — wrap everything as a single slide
        body = _collect_body_lines(markdown, 0)
        return [Slide(heading=title or "Article", body_lines=body)]

    slides: list[Slide] = []

    # Text before the first heading becomes an intro slide
    first_heading_start = headings[0].start()
    if first_heading_start > 0:
        intro_body = _collect_body_lines(markdown, 0, first_heading_start)
        if intro_body:
            slides.append(Slide(heading=title or "Introduction", body_lines=intro_body))

    for idx, match in enumerate(headings):
        heading = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(markdown)
        body = _collect_body_lines(markdown, start, end)
        slides.append(Slide(heading=heading, body_lines=body))

    return slides


def _collect_body_lines(text: str, start: int, end: int | None = None) -> list[str]:
    """Collect non-empty, non-heading lines from the text range."""
    if end is None:
        end = len(text)
    segment = text[start:end].strip()
    if not segment:
        return []
    lines: list[str] = []
    for line in segment.splitlines():
        stripped = line.strip()
        if stripped and not _HEADING_RE.match(stripped):
            lines.append(stripped)
    return lines
