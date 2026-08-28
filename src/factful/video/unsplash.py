"""Unsplash-backed image source for slide backgrounds."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx

from factful.video.relevance import keyword_overlap, noun_jaccard
from factful.video.sources import ImageSourceError

_UNSPLASH_API = "https://api.unsplash.com"
_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3

_IMAGE_CACHE_DIR = Path("factful_videos/images")


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

        # Quick check: try a lightweight search to confirm connectivity
        query = self._build_query(heading)
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

        query = self._build_query(heading)

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.get(
                    f"{_UNSPLASH_API}/photos/random",
                    params={
                        "query": query,
                        "orientation": "landscape",
                        "content_filter": "high",
                        "count": 1,
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
                if not data:
                    # Broaden query on retry
                    query = self._broaden_query(query)
                    continue

                photo = data[0] if isinstance(data, list) else data
                tags = [t["title"] for t in photo.get("tags", [])]
                alt_description = photo.get("alt_description")

                # Check relevance
                if self._relevance_mode == "noun_jaccard":
                    relevant = noun_jaccard(heading, alt_description)
                else:
                    relevant = keyword_overlap(heading, tags)

                if not relevant:
                    if attempt < _MAX_RETRIES - 1:
                        # Still have retries — broaden and try again
                        query = self._broaden_query(query)
                        continue
                    # Last attempt: accept the image even if relevance is
                    # marginal — we've broadened the query as far as we can
                    pass

                # Download the image
                download_url = photo["urls"]["raw"]
                return self._download(download_url, output_path)

            except httpx.HTTPError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise ImageSourceError(
                        f"failed to fetch image for slide '{heading}' after "
                        f"{_MAX_RETRIES} attempts: {exc}"
                    ) from exc
                # Broaden query and retry
                query = self._broaden_query(query)

        raise ImageSourceError(
            f"no relevant image found for '{heading}' after {_MAX_RETRIES} attempts"
        )

    def _build_query(self, heading: str) -> str:
        """Convert a heading into an Unsplash search query."""
        from factful.video.relevance import _tokenize

        # Strip leading instruction/imperative words that signal the heading
        # is a user prompt rather than a searchable topic phrase.
        heading = re.sub(
            r"^(story about|a story about|research|investigate|explore|analyze"
            r"|describe|explain|discuss|read|bring|include)\s+",
            "",
            heading,
            flags=re.IGNORECASE,
        )
        tokens = _tokenize(heading)
        return " ".join(tokens[:5]) if tokens else "trending"

    def _broaden_query(self, query: str) -> str:
        """Return a broader version of the query for retry."""
        tokens = query.split()
        if len(tokens) <= 1:
            return "trending"
        return " ".join(tokens[:-1])  # drop last word

    def _download(self, url: str, output_path: Path) -> Path:
        """Download an image from *url* to *output_path*, with caching."""
        # Check cache
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _IMAGE_CACHE_DIR / f"{url_hash}.jpg"
        if cache_path.exists():
            import shutil

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, output_path)
            return output_path

        # Download
        resp = self._client.get(url)
        resp.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)

        # Cache
        cache_path.write_bytes(resp.content)
        return output_path
