"""Pluggable image source protocol for slide backgrounds."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class ImageSourceError(Exception):
    """Raised when an ImageSource cannot produce an image for a slide.

    Must include a descriptive message identifying the slide and the reason.
    """


@runtime_checkable
class ImageSource(Protocol):
    """Pluggable image provider for slide backgrounds.

    Every implementation must fail hard on unrecoverable errors.
    No silent fallback, no placeholder images.
    """

    def fetch(
        self,
        *,
        heading: str,
        body: str,
        output_path: Path,
    ) -> Path:
        """Download or generate an image and write it to *output_path*.

        Args:
            heading: The slide heading (used for search query or prompt).
            body: The slide body text (combined context for AI generation).
            output_path: Where to write the image file (e.g. .jpg).

        Returns:
            output_path on success.

        Raises:
            ImageSourceError: on any failure. The caller never silently
                substitutes a default image.
        """
        ...

    def validate(self, *, heading: str, body: str) -> str | None:
        """Best-effort pre-validation before any rendering work begins.

        Args:
            heading: The slide heading.
            body: The slide body text.

        Returns:
            None if fetch() would likely succeed, or an error message
            string explaining why it would fail.
        """
        ...
