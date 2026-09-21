"""Background music selection from the Openverse Audio API.

v1 is CC0-only and anonymous (no API key): ``MusicSelector`` searches
Openverse, filters out anything that is not CC0 or shorter than a minimum,
downloads the winning track, and returns its path for the composer to mix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from factful.video.exceptions import MusicSourceError

logger = logging.getLogger(__name__)

_OPENVERSE_AUDIO_URL = "https://api.openverse.org/v1/audio/"
_DEFAULT_MOOD_QUERY = "cinematic ambient"
_MOOD_QUERIES: dict[str, str] = {
    "neutral": "ambient background",
    "inspirational": "uplifting",
    "analytical": "documentary ambient",
    "urgent": "tension",
    "calm": "calm ambient",
}
_ALLOWED_EXTENSIONS = frozenset({"mp3", "ogg", "wav", "flac", "m4a", "webm"})
_ANON_MAX_PAGE_SIZE = 20


@dataclass
class MusicTrack:
    """A downloaded background track and its provenance.

    Attributes:
        path: Local audio file ready for the composer.
        title: Track title from Openverse.
        creator: Track creator from Openverse.
        license: License id (always ``cc0`` for v1).
        source_url: Openverse landing page for the track.
    """

    path: Path
    title: str
    creator: str
    license: str
    source_url: str


def mood_query(mood: str) -> str:
    """Return the Openverse search query for a script ``music_mood``."""
    return _MOOD_QUERIES.get(mood, _DEFAULT_MOOD_QUERY)


class MusicSelector:
    """Search Openverse for a CC0 background track and download it.

    Args:
        _http_client: Optional injected ``httpx.Client`` (for tests).
        license_id: Required license id (default ``cc0``).
        min_duration_seconds: Minimum acceptable track duration.
        max_duration_seconds: Preferred upper bound on track duration, to
            avoid downloading a very long file.
        max_candidates: How many results to request per search.
        base_url: Openverse audio search endpoint.
        timeout: HTTP timeout for the default client.
    """

    def __init__(
        self,
        *,
        _http_client: httpx.Client | None = None,
        license_id: str = "cc0",
        min_duration_seconds: int = 120,
        max_duration_seconds: int = 300,
        max_candidates: int = 20,
        base_url: str = _OPENVERSE_AUDIO_URL,
        timeout: float = 30.0,
    ) -> None:
        self._client = _http_client or httpx.Client(timeout=timeout)
        self._license_id = license_id
        self._min_duration_ms = min_duration_seconds * 1000
        self._max_duration_ms = max_duration_seconds * 1000
        if max_candidates > _ANON_MAX_PAGE_SIZE:
            logger.warning(
                "max_candidates=%d exceeds the anonymous Openverse limit; using %d",
                max_candidates,
                _ANON_MAX_PAGE_SIZE,
            )
            max_candidates = _ANON_MAX_PAGE_SIZE
        self._max_candidates = max_candidates
        self._base_url = base_url

    def select(self, mood: str, dest_dir: Path) -> MusicTrack:
        """Return a downloaded CC0 track matching *mood*.

        Args:
            mood: The script's ``music_mood``.
            dest_dir: Directory to download into (cached by track id).

        Returns:
            The downloaded ``MusicTrack``.

        Raises:
            MusicSourceError: if the search fails or no usable CC0 track
                is found, or the download fails.
        """
        query = mood_query(mood)
        results = self._search(query)
        try:
            track = self._best_usable(results)
        except MusicSourceError:
            if query == _DEFAULT_MOOD_QUERY:
                raise
            logger.info(
                "No usable CC0 track for mood %r; retrying with %r",
                mood,
                _DEFAULT_MOOD_QUERY,
            )
            track = self._best_usable(self._search(_DEFAULT_MOOD_QUERY))

        track_id = str(track["id"])
        extension = str(track.get("filetype") or "mp3").lower()
        if extension not in _ALLOWED_EXTENSIONS:
            extension = "mp3"
        dest = dest_dir / f"music_{track_id}.{extension}"

        if not dest.exists():
            self._download(str(track["url"]), dest)

        return MusicTrack(
            path=dest,
            title=str(track.get("title") or ""),
            creator=str(track.get("creator") or ""),
            license=self._license_id,
            source_url=str(track.get("foreign_landing_url") or track["url"]),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self, query: str) -> list[dict[str, object]]:
        params: dict[str, str | int] = {
            "q": query,
            "license": self._license_id,
            "page_size": self._max_candidates,
        }
        try:
            response = self._client.get(self._base_url, params=params)
        except httpx.RequestError as exc:
            raise MusicSourceError(f"Openverse request failed: {exc}") from exc

        if response.status_code != 200:
            raise MusicSourceError(f"Openverse API error (HTTP {response.status_code})")

        try:
            data = response.json()
        except ValueError as exc:
            raise MusicSourceError("Openverse returned malformed JSON") from exc

        results = data.get("results")
        if not isinstance(results, list):
            raise MusicSourceError("Openverse returned no results field")
        return [r for r in results if isinstance(r, dict)]

    def _best_usable(self, results: list[dict[str, object]]) -> dict[str, object]:
        """Pick a long-enough track, avoiding oversized downloads.

        Preference is the longest track within ``[min, max]`` duration so a
        single track covers more of the video. Tracks longer than the cap are
        only used when nothing in range exists, and then the least oversized
        one is chosen to keep the download manageable.
        """
        usable: list[tuple[int, dict[str, object]]] = []
        for track in results:
            if track.get("license") != self._license_id:
                continue
            if not track.get("url"):
                continue
            raw_duration = track.get("duration")
            if not isinstance(raw_duration, (int, float, str)):
                continue
            try:
                duration = int(raw_duration)
            except ValueError:
                continue
            if duration < self._min_duration_ms:
                continue
            usable.append((duration, track))
        if not usable:
            raise MusicSourceError(f"no usable {self._license_id} music track found")
        in_range = [item for item in usable if item[0] <= self._max_duration_ms]
        if in_range:
            return max(in_range, key=lambda item: item[0])[1]
        return min(usable, key=lambda item: item[0])[1]

    def _download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        except (httpx.RequestError, OSError) as exc:
            raise MusicSourceError(f"failed to download music from {url}: {exc}") from exc


def select_music(
    selector: MusicSelector | None,
    *,
    enabled: bool,
    mood: str,
    dest_dir: Path,
) -> Path | None:
    """Resolve an optional background-music path for a render.

    Music is a nice-to-have: when disabled, unconfigured, or unavailable
    the render continues without it (the failure is logged, not swallowed).

    Returns:
        The track path, or ``None`` to compose without music.
    """
    if not enabled or selector is None:
        return None
    try:
        return selector.select(mood, dest_dir).path
    except MusicSourceError as exc:
        logger.warning("Background music unavailable (%s); composing without music", exc)
        return None
