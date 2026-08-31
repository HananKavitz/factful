"""Unsplash-backed image source for slide backgrounds."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import httpx

from factful.video.relevance import _extract_nouns, _tokenize
from factful.video.sources import ImageSourceError

_UNSPLASH_API = "https://api.unsplash.com"
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_SEARCH_PER_PAGE = 20
_RELEVANCE_THRESHOLD = 0.3

_IMAGE_CACHE_DIR = Path("factful_videos/images")

# Headings that carry no searchable topic and should be ignored in favour
# of the slide body or a broader fallback.
_GENERIC_CONTENT_WORDS: frozenset[str] = frozenset(
    {
        "introduction",
        "intro",
        "overview",
        "background",
        "conclusion",
        "closing",
        "summary",
        "wrap",
        "wrapping",
        "bottom",
        "line",
        "final",
        "thoughts",
        "key",
        "takeaways",
        "recap",
        "next",
        "steps",
        "big",
        "picture",
        "brief",
        "what",
        "means",
    }
)


class UnsplashSource:
    """Image source that searches Unsplash for relevant photos.

    Args:
        api_key: Unsplash API access key.
        relevance_mode: ``"keyword"`` (default) or ``"noun_jaccard"``.
        http_client: Optional pre-configured httpx client (for testing).
    """

    def __init__(
        self,
        api_key: str,
        relevance_mode: str = "keyword",
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._relevance_mode = relevance_mode
        self._client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def validate(self, *, heading: str, body: str) -> str | None:
        if not self._api_key:
            return "Unsplash API key not configured"

        query = self._build_query(heading, body)
        try:
            resp = self._client.get(
                f"{_UNSPLASH_API}/search/photos",
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "landscape",
                    "content_filter": "high",
                },
                headers={"Authorization": f"Client-ID {self._api_key}"},
            )
            if resp.status_code == 403:
                return "Unsplash API key is invalid or rate-limited"
            if resp.status_code == 404:
                return "Unsplash endpoint not found"
            resp.raise_for_status()
            data = resp.json()
            if not data.get("results"):
                return f"no Unsplash images found for query '{query}'"
            return None
        except httpx.HTTPError as exc:
            return f"Unsplash API error during validation: {exc}"

    def fetch(
        self,
        *,
        heading: str,
        body: str,
        output_path: Path,
    ) -> Path:
        if not self._api_key:
            raise ImageSourceError(f"Unsplash API key not configured (slide: '{heading}')")

        query = self._build_query(heading, body)

        best_url: str | None = None
        best_score = -1.0

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.get(
                    f"{_UNSPLASH_API}/search/photos",
                    params={
                        "query": query,
                        "per_page": _SEARCH_PER_PAGE,
                        "orientation": "landscape",
                        "content_filter": "high",
                    },
                    headers={"Authorization": f"Client-ID {self._api_key}"},
                )
                if resp.status_code == 403:
                    raise ImageSourceError(f"Unsplash API key rejected for slide '{heading}'")
                if resp.status_code == 404:
                    raise ImageSourceError(
                        f"no Unsplash images found for query '{query}' (slide: '{heading}')"
                    )
                resp.raise_for_status()

                data = resp.json()
                results = data.get("results", [])
                if not results:
                    if attempt < _MAX_RETRIES - 1:
                        query = self._broaden_query(query)
                        continue
                    break

                for photo in results:
                    score = self._score_relevance(query, photo)
                    if score > best_score:
                        best_score = score
                        best_url = photo["urls"]["raw"]

                if best_score >= _RELEVANCE_THRESHOLD and best_url:
                    return self._download(best_url, output_path)

                if attempt < _MAX_RETRIES - 1:
                    query = self._broaden_query(query)

            except httpx.HTTPError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise ImageSourceError(
                        f"failed to fetch image for slide '{heading}' after "
                        f"{_MAX_RETRIES} attempts: {exc}"
                    ) from exc
                query = self._broaden_query(query)

        if best_url:
            return self._download(best_url, output_path)

        raise ImageSourceError(
            f"no relevant image found for '{heading}' after {_MAX_RETRIES} attempts"
        )

    def _build_query(self, heading: str, body: str = "") -> str:
        """Convert a heading and body into an Unsplash search query."""
        heading = re.sub(
            r"^(story about|a story about|research|investigate|explore|analyze"
            r"|describe|explain|discuss|read|bring|include)\s+",
            "",
            heading,
            flags=re.IGNORECASE,
        )
        h_tokens = _tokenize(heading)
        b_tokens = _tokenize(body)

        if self._is_generic_heading(heading) or not h_tokens:
            return " ".join(b_tokens[:6]) if b_tokens else "trending"

        seen = set(h_tokens)
        combined = h_tokens + [t for t in b_tokens if t not in seen]
        return " ".join(combined[:6]) if combined else "trending"

    def _is_generic_heading(self, heading: str) -> bool:
        """Return True if the heading contains no searchable topic words."""
        tokens = _tokenize(heading)
        if not tokens:
            return True
        meaningful = [t for t in tokens if t not in _GENERIC_CONTENT_WORDS]
        return len(meaningful) == 0

    def _broaden_query(self, query: str) -> str:
        """Return a broader version of the query for retry."""
        tokens = query.split()
        if len(tokens) <= 1:
            return "trending"
        return " ".join(tokens[:-1])

    def _score_relevance(self, query_text: str, photo: dict[str, Any]) -> float:
        """Score a photo's relevance to the query text (0.0–1.0)."""
        photo_text = self._photo_text(photo)
        if self._relevance_mode == "noun_jaccard":
            heading_nouns = _extract_nouns(query_text)
            if not heading_nouns:
                return 1.0
            desc_nouns = _extract_nouns(photo_text)
            if not desc_nouns:
                return 0.0
            union = heading_nouns | desc_nouns
            intersection = heading_nouns & desc_nouns
            return len(intersection) / len(union)

        query_tokens = set(_tokenize(query_text))
        if not query_tokens:
            return 1.0
        text_tokens = set(_tokenize(photo_text))
        if not text_tokens:
            return 0.0
        overlap = query_tokens & text_tokens
        return len(overlap) / len(query_tokens)

    def _photo_text(self, photo: dict[str, Any]) -> str:
        """Combine all searchable text from a photo into one string."""
        parts: list[str] = []
        for tag in photo.get("tags", []):
            if isinstance(tag, dict) and "title" in tag:
                parts.append(tag["title"])
        for key in ("alt_description", "description"):
            val = photo.get(key)
            if val:
                parts.append(str(val))
        return " ".join(parts)

    def _download(self, url: str, output_path: Path) -> Path:
        """Download an image from *url* to *output_path*, with caching."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _IMAGE_CACHE_DIR / f"{url_hash}.jpg"
        if cache_path.exists():
            import shutil

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, output_path)
            return output_path

        resp = self._client.get(url)
        resp.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)

        cache_path.write_bytes(resp.content)
        return output_path
