"""Tests for background music selection (Openverse, CC0 only)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from factful.video.exceptions import MusicSourceError
from factful.video.music import MusicSelector, MusicTrack, select_music

_AUDIO_URL = "https://api.openverse.org/v1/audio/"


def _result(
    *,
    track_id: str = "abc-123",
    license_id: str = "cc0",
    duration_ms: int = 120_000,
    url: str | None = "https://cdn.example/track.mp3",
    filetype: str = "mp3",
    title: str = "Calm Ambient",
    creator: str = "Someone",
) -> dict[str, object]:
    return {
        "id": track_id,
        "title": title,
        "creator": creator,
        "license": license_id,
        "duration": duration_ms,
        "url": url,
        "filetype": filetype,
        "foreign_landing_url": f"https://example/{track_id}",
    }


def _selector(
    results: list[dict[str, object]],
    *,
    captured: dict[str, object] | None = None,
    downloads: dict[str, int] | None = None,
    status: int = 200,
    raise_on_download: bool = False,
    max_candidates: int = 8,
    max_duration_seconds: int = 600,
) -> MusicSelector:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audio/"):
            if captured is not None:
                captured["params"] = dict(request.url.params)
            return httpx.Response(status, json={"results": results})
        if downloads is not None:
            downloads["count"] = downloads.get("count", 0) + 1
        if raise_on_download:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=b"audio-bytes")

    return MusicSelector(
        _http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        min_duration_seconds=30,
        max_candidates=max_candidates,
        max_duration_seconds=max_duration_seconds,
    )


class TestMusicSelectorSearch:
    def test_maps_mood_to_query(self, tmp_path: Path) -> None:
        """RED: each mood maps to its own Openverse search query."""
        captured: dict[str, object] = {}
        selector = _selector([_result()], captured=captured)

        selector.select("analytical", tmp_path)

        assert captured["params"]["q"] == "documentary ambient"  # type: ignore[index]

    def test_unknown_mood_uses_default_query(self, tmp_path: Path) -> None:
        """RED: an unexpected mood falls back to a sane default query."""
        captured: dict[str, object] = {}
        selector = _selector([_result()], captured=captured)

        selector.select("mysterious", tmp_path)

        assert captured["params"]["q"] == "cinematic ambient"  # type: ignore[index]

    def test_requests_cc0_license_only(self, tmp_path: Path) -> None:
        """RED: v1 is CC0-only, so the API request must filter to cc0."""
        captured: dict[str, object] = {}
        selector = _selector([_result()], captured=captured)

        selector.select("calm", tmp_path)

        assert captured["params"]["license"] == "cc0"  # type: ignore[index]

    def test_clamps_page_size_to_anonymous_limit(self, tmp_path: Path) -> None:
        """RED: anonymous Openverse rejects page_size > 20 with a 401."""
        captured: dict[str, object] = {}
        selector = _selector([_result()], captured=captured, max_candidates=50)

        selector.select("calm", tmp_path)

        assert captured["params"]["page_size"] == "20"  # type: ignore[index]

    def test_falls_back_to_default_query_when_mood_is_barren(self, tmp_path: Path) -> None:
        """RED: a mood query with no usable CC0 track retries the default query."""
        queries: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/audio/"):
                return httpx.Response(200, content=b"audio-bytes")
            q = request.url.params["q"]
            queries.append(q)
            if q == "documentary ambient":
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"results": [_result()]})

        selector = MusicSelector(_http_client=httpx.Client(transport=httpx.MockTransport(handler)))

        track = selector.select("analytical", tmp_path)

        assert track.license == "cc0"
        assert queries == ["documentary ambient", "cinematic ambient"]


class TestMusicSelectorSelect:
    def test_downloads_track_and_returns_metadata(self, tmp_path: Path) -> None:
        """RED: a valid CC0 result is downloaded and described by a MusicTrack."""
        selector = _selector([_result(title="Deep Focus", creator="Ann")])

        track = selector.select("calm", tmp_path)

        assert isinstance(track, MusicTrack)
        assert track.path.exists()
        assert track.path.read_bytes() == b"audio-bytes"
        assert track.title == "Deep Focus"
        assert track.creator == "Ann"
        assert track.license == "cc0"

    def test_skips_non_cc0_and_short_results(self, tmp_path: Path) -> None:
        """RED: defensive filtering keeps only CC0 tracks above the min duration."""
        results = [
            _result(track_id="nc", license_id="by-nc", duration_ms=120_000),
            _result(track_id="short", license_id="cc0", duration_ms=5_000),
            _result(track_id="good", license_id="cc0", duration_ms=120_000),
        ]
        selector = _selector(results)

        track = selector.select("calm", tmp_path)

        assert "good" in track.path.name

    def test_reuses_cached_download(self, tmp_path: Path) -> None:
        """RED: re-selecting the same track must not re-download it."""
        downloads = {"count": 0}
        selector = _selector([_result()], downloads=downloads)

        first = selector.select("calm", tmp_path)
        second = selector.select("calm", tmp_path)

        assert first.path == second.path
        assert downloads["count"] == 1

    def test_prefers_longest_usable_candidate(self, tmp_path: Path) -> None:
        """RED: the longest usable CC0 track is chosen to minimize looping."""
        results = [
            _result(track_id="short", duration_ms=60_000),
            _result(track_id="long", duration_ms=300_000),
            _result(track_id="mid", duration_ms=120_000),
        ]
        selector = _selector(results)

        track = selector.select("calm", tmp_path)

        assert "long" in track.path.name

    def test_prefers_longest_within_max_duration(self, tmp_path: Path) -> None:
        """RED: an oversized track is skipped in favor of the longest in-range one."""
        results = [
            _result(track_id="huge", duration_ms=1_800_000),
            _result(track_id="inrange", duration_ms=420_000),
            _result(track_id="tiny", duration_ms=200_000),
        ]
        selector = _selector(results, max_duration_seconds=600)

        track = selector.select("calm", tmp_path)

        assert "inrange" in track.path.name

    def test_falls_back_to_shortest_when_all_exceed_max(self, tmp_path: Path) -> None:
        """RED: when every track exceeds the cap, pick the least oversized one."""
        results = [
            _result(track_id="huge", duration_ms=1_800_000),
            _result(track_id="huger", duration_ms=3_600_000),
        ]
        selector = _selector(results, max_duration_seconds=600)

        track = selector.select("calm", tmp_path)

        assert "huge" in track.path.name
        assert "huger" not in track.path.name

    def test_no_usable_candidate_raises(self, tmp_path: Path) -> None:
        """RED: a search with no usable CC0 track fails loudly."""
        selector = _selector([_result(license_id="by-nc")])

        with pytest.raises(MusicSourceError, match="no usable"):
            selector.select("calm", tmp_path)

    def test_empty_results_raises(self, tmp_path: Path) -> None:
        """RED: an empty result set fails loudly."""
        selector = _selector([])

        with pytest.raises(MusicSourceError, match="no usable"):
            selector.select("calm", tmp_path)

    def test_search_http_error_raises(self, tmp_path: Path) -> None:
        """RED: a non-200 search response is surfaced as MusicSourceError."""
        selector = _selector([_result()], status=500)

        with pytest.raises(MusicSourceError, match="Openverse"):
            selector.select("calm", tmp_path)

    def test_download_failure_raises(self, tmp_path: Path) -> None:
        """RED: a failed download is surfaced as MusicSourceError."""
        selector = _selector([_result()], raise_on_download=True)

        with pytest.raises(MusicSourceError, match="download"):
            selector.select("calm", tmp_path)


class TestSelectMusicHelper:
    def test_disabled_returns_none(self, tmp_path: Path) -> None:
        """RED: music_enabled=False composes without music."""
        selector = _selector([_result()])

        assert select_music(selector, enabled=False, mood="calm", dest_dir=tmp_path) is None

    def test_missing_selector_returns_none(self, tmp_path: Path) -> None:
        """RED: no configured selector means no music."""
        assert select_music(None, enabled=True, mood="calm", dest_dir=tmp_path) is None

    def test_source_error_returns_none(self, tmp_path: Path) -> None:
        """RED: music is optional, so a source failure must not fail the render."""
        selector = _selector([])

        assert select_music(selector, enabled=True, mood="calm", dest_dir=tmp_path) is None
