"""Tests for the StockGenerator (Pexels stock footage)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import httpx
import pytest

from factful.video.exceptions import NoUsableClipsError, VideoSourceError
from factful.video.generators.stock import StockGenerator
from factful.video.interfaces import VideoOutput, VideoRequest, VideoScript
from factful.video.music import MusicSelector, MusicTrack
from factful.video.narration import NarrationTrack
from factful.video.script_director import SceneOut, ScriptDirector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MARKDOWN = "# Hello\n\nWorld."
SAMPLE_TITLE = "Hello World"


@pytest.fixture
def settings() -> dict[str, Any]:
    return {
        "stock_api_key": "test_key_123",
        "stock_provider": "pexels",
        "stock_min_resolution": "1080p",
        "width": 1920,
        "height": 1080,
        "fps": 30,
    }


def _pexels_response_json(*, total_results: int = 5) -> dict[str, Any]:
    return {
        "total_results": total_results,
        "page": 1,
        "per_page": 15,
        "videos": [
            {
                "id": 1000 + i,
                "width": 1920,
                "height": 1080,
                "duration": 10,
                "video_files": [
                    {
                        "id": 2000 + i,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "link": f"https://example.com/clip{i}.mp4",
                    },
                    {
                        "id": 3000 + i,
                        "quality": "sd",
                        "file_type": "video/mp4",
                        "width": 640,
                        "height": 480,
                        "link": f"https://example.com/clip{i}_sd.mp4",
                    },
                ],
            }
            for i in range(min(total_results, 3))
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStockGeneratorName:
    def test_name_returns_stock(self) -> None:
        """RED: the strategy name should be 'stock'."""
        gen = StockGenerator(pexels_api_key="key", script_director=MagicMock())
        assert gen.name() == "stock"


class TestStockGeneratorSearch:
    """Focus on the Pexels search logic in isolation."""

    def test_successful_search_returns_video_urls(self) -> None:
        """RED: a 200 response with videos should yield download URLs."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _pexels_response_json(total_results=3)
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        urls = gen._search_pexels("sunset ocean", min_results=1)
        assert len(urls) >= 1
        assert all(c.link.startswith("https://") for c in urls)

    def test_search_sends_correct_headers(self) -> None:
        """RED: the Pexels API call should include the auth header."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _pexels_response_json(total_results=1)
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="secret_key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        gen._search_pexels("nature", min_results=1)
        _call_kwargs = mock_client.get.call_args.kwargs or {}
        headers = _call_kwargs.get("headers", {})
        assert headers.get("Authorization") == "secret_key"

    def test_search_sends_correct_query_params(self) -> None:
        """RED: the API call should include query, per_page, orientation, size."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _pexels_response_json(total_results=1)
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        gen._search_pexels("city skyline", min_results=1)
        _call_kwargs = mock_client.get.call_args.kwargs or {}
        params = _call_kwargs.get("params", {})
        assert "city" in params.get("query", "") and "skyline" in params.get("query", "")
        assert params.get("per_page") == 15
        assert params.get("page") == 1
        assert params.get("orientation") == "landscape"
        assert params.get("size") == "medium"

    def test_search_prefers_smallest_1080p_candidate(self) -> None:
        """RED: rank 1080p ahead of 4K to avoid huge downloads."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_results": 1,
            "videos": [
                {
                    "id": 1,
                    "width": 3840,
                    "height": 2160,
                    "duration": 10,
                    "video_files": [
                        {"width": 3840, "height": 2160, "link": "https://example.com/4k.mp4"},
                        {"width": 1920, "height": 1080, "link": "https://example.com/1080p.mp4"},
                    ],
                }
            ],
        }
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        urls = gen._search_pexels("x", min_results=1)
        assert urls[0].links == ("https://example.com/1080p.mp4", "https://example.com/4k.mp4")

    def test_search_preserves_pexels_relevance_order(self) -> None:
        """RED: videos keep Pexels relevance order; resolution only ranks files within a video."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_results": 2,
            "videos": [
                {
                    "id": 1,
                    "width": 2560,
                    "height": 1440,
                    "duration": 10,
                    "video_files": [
                        {
                            "width": 2560,
                            "height": 1440,
                            "link": "https://example.com/top_hit.mp4",
                        }
                    ],
                },
                {
                    "id": 2,
                    "width": 1920,
                    "height": 1080,
                    "duration": 10,
                    "video_files": [
                        {
                            "width": 1920,
                            "height": 1080,
                            "link": "https://example.com/less_relevant.mp4",
                        }
                    ],
                },
            ],
        }
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        urls = gen._search_pexels("x", min_results=1)
        assert urls[0].link == "https://example.com/top_hit.mp4"
        assert urls[1].link == "https://example.com/less_relevant.mp4"

    def test_search_zero_results_returns_empty(self) -> None:
        """RED: when Pexels returns 0 results, an empty list is returned."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _pexels_response_json(total_results=0)
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        urls = gen._search_pexels("unicorn", min_results=0)
        assert urls == []

    def test_search_http_error_raises(self) -> None:
        """RED: a non-200 response should raise VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="bad_key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        with pytest.raises(VideoSourceError, match="Pexels API error"):
            gen._search_pexels("nature", min_results=1)

    def test_search_network_error_raises(self) -> None:
        """RED: a network error should raise VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.RequestError("connection refused")

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        with pytest.raises(VideoSourceError, match="Pexels request failed"):
            gen._search_pexels("nature", min_results=1)


class TestStockGeneratorSelectClip:
    def test_selects_highest_resolution(self) -> None:
        """RED: the best clip is the one with the largest pixel count."""
        gen = StockGenerator(pexels_api_key="key", script_director=MagicMock())
        videos = [
            {"width": 640, "height": 480, "link": "https://example.com/sd.mp4"},
            {"width": 1920, "height": 1080, "link": "https://example.com/hd.mp4"},
            {"width": 1280, "height": 720, "link": "https://example.com/mid.mp4"},
        ]
        best = gen._select_best_clip(videos)
        assert best is not None
        assert best["link"] == "https://example.com/hd.mp4"

    def test_select_returns_none_for_empty_list(self) -> None:
        """RED: empty input should return None."""
        gen = StockGenerator(pexels_api_key="key", script_director=MagicMock())
        assert gen._select_best_clip([]) is None


class TestStockGeneratorDownload:
    def test_download_writes_file(self, tmp_path: Path) -> None:
        """RED: a downloaded clip should be written to the target path."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        type(mock_response).content = PropertyMock(return_value=b"clip data")
        mock_client.get.return_value = mock_response

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        dest = tmp_path / "clip.mp4"
        result = gen._download_clip("https://example.com/clip.mp4", dest)
        assert result == dest
        assert dest.read_bytes() == b"clip data"

    def test_download_network_failure_raises(self, tmp_path: Path) -> None:
        """RED: a failed download should raise VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.RequestError("timeout")

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
        )

        dest = tmp_path / "clip.mp4"
        with pytest.raises(VideoSourceError, match="failed to download"):
            gen._download_clip("https://example.com/clip.mp4", dest)


class TestStockGeneratorRanker:
    """The injected ranker decides which candidates are downloaded."""

    def test_downloads_rankers_top_choice(self, tmp_path: Path) -> None:
        """RED: the ranker's preferred candidate is downloaded, not Pexels' first."""
        from factful.video.rankers import PexelsCandidate

        search_resp = MagicMock(spec=httpx.Response)
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "total_results": 2,
            "videos": [
                {
                    "id": 1,
                    "image": "https://img/1.jpg",
                    "video_files": [
                        {
                            "width": 1920,
                            "height": 1080,
                            "link": "https://example.com/first.mp4",
                        }
                    ],
                },
                {
                    "id": 2,
                    "image": "https://img/2.jpg",
                    "video_files": [
                        {
                            "width": 1920,
                            "height": 1080,
                            "link": "https://example.com/second.mp4",
                        }
                    ],
                },
            ],
        }
        downloaded: list[str] = []

        def _get(url: str, *args: Any, **kwargs: Any) -> Any:
            if "search" in url:
                return search_resp
            downloaded.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b"clip"
            return resp

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = _get

        ranker = MagicMock()
        ranker.rank.return_value = [
            PexelsCandidate(
                video_id=2,
                thumbnail_url="https://img/2.jpg",
                links=("https://example.com/second.mp4",),
            )
        ]

        trimmed = tmp_path / "scene_0000_trimmed.mp4"
        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
            _trim=MagicMock(return_value=trimmed),
            _placeholder=MagicMock(),
            ranker=ranker,
        )
        scene = SceneOut(
            narration="Ocean waves crash.",
            visual_keywords=["ocean"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )

        result = gen._fetch_scene_clip(scene, 0, tmp_path, 5.0, set(), set(), "Title")

        assert result == trimmed
        assert downloaded == ["https://example.com/second.mp4"]

    def test_no_acceptable_candidate_uses_placeholder(self, tmp_path: Path) -> None:
        """RED: an empty ranker result gates the scene to a placeholder, no download."""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.status_code = 200
        search_resp.json.return_value = _pexels_response_json(total_results=1)
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = search_resp

        ranker = MagicMock()
        ranker.rank.return_value = []
        placeholder = tmp_path / "ph.mp4"
        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
            _placeholder=MagicMock(return_value=placeholder),
            _trim=MagicMock(),
            ranker=ranker,
        )
        scene = SceneOut(
            narration="Unrelated concept.",
            visual_keywords=["unicorn"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )

        result = gen._fetch_scene_clip(scene, 0, tmp_path, 5.0, set(), set(), "Title")

        assert result == placeholder
        assert mock_client.get.call_count == 1  # search only, no download


class TestStockGeneratorFetchRetry:
    """A failed clip download falls through to the next candidate."""

    def test_retries_next_candidate_on_download_failure(self, tmp_path: Path) -> None:
        """RED: a timeout on the first URL uses the next fresh candidate."""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "total_results": 1,
            "videos": [
                {
                    "id": 1,
                    "width": 1920,
                    "height": 1080,
                    "duration": 10,
                    "video_files": [
                        {"width": 1920, "height": 1080, "link": "https://example.com/bad.mp4"},
                        {"width": 1920, "height": 1080, "link": "https://example.com/good.mp4"},
                    ],
                }
            ],
        }

        good_resp = MagicMock(spec=httpx.Response)
        good_resp.status_code = 200
        type(good_resp).content = PropertyMock(return_value=b"clip")

        def _get(url: str, *args: Any, **kwargs: Any) -> Any:
            if "search" in url:
                return search_resp
            if url.endswith("/bad.mp4"):
                raise httpx.RequestError("timeout")
            return good_resp

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = _get

        trimmed = tmp_path / "scene_0000_trimmed.mp4"
        mock_placeholder = MagicMock()
        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _http_client=mock_client,
            _trim=MagicMock(return_value=trimmed),
            _placeholder=mock_placeholder,
        )

        scene = SceneOut(
            narration="Ocean waves crash on the shore.",
            visual_keywords=["ocean"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )

        result = gen._fetch_scene_clip(scene, 0, tmp_path, 5.0, set(), set(), "Title")

        assert result == trimmed
        mock_placeholder.assert_not_called()


# ---------------------------------------------------------------------------
# Integration-style: full generate() with all mocks
# ---------------------------------------------------------------------------


class TestStockGeneratorGenerate:
    """End-to-end generate() with all collaborators mocked."""

    def _track(self, tmp_path: Path, durations: list[float]) -> NarrationTrack:
        audio = tmp_path / "voiceover.wav"
        audio.write_bytes(b"wav")
        meta = tmp_path / "voiceover.jsonl"
        meta.write_text("", encoding="utf-8")
        return NarrationTrack(audio_path=audio, metadata_path=meta, durations=durations)

    async def test_generate_returns_video_output(self, tmp_path: Path) -> None:
        """RED: successful generation returns a VideoOutput."""
        scene = SceneOut(
            narration="A test scene.",
            visual_keywords=["sunset"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(scenes=[scene], music_mood="neutral", overall_pace="moderate")

        mock_http = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _pexels_response_json(total_results=1)
        type(mock_resp).content = PropertyMock(return_value=b"data")
        mock_http.get.return_value = mock_resp

        mock_dir = MagicMock(spec=ScriptDirector)
        mock_dir.analyze.return_value = script

        mock_narration = AsyncMock(return_value=self._track(tmp_path, [5.0]))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
            _narration=mock_narration,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
        )

        assert isinstance(output, VideoOutput)
        assert output.video_path == tmp_path / "final.mp4"

    async def test_generate_empty_script_raises(self, tmp_path: Path) -> None:
        """RED: when script director returns no scenes, NoUsableClipsError is raised."""
        mock_dir = MagicMock(spec=ScriptDirector)
        mock_dir.analyze.return_value = VideoScript(
            scenes=[], music_mood="neutral", overall_pace="moderate"
        )

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
        )

        with pytest.raises(NoUsableClipsError, match="no scenes"):
            await gen.generate(
                VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
                tmp_path / "final.mp4",
            )

    async def test_generate_uses_placeholder_when_no_clips(self, tmp_path: Path) -> None:
        """RED: a scene with no Pexels result still gets a sized placeholder."""
        scene = SceneOut(
            narration="A scene.",
            visual_keywords=["unicorn", "rainbow"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(scenes=[scene], music_mood="neutral", overall_pace="moderate")

        mock_http = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _pexels_response_json(total_results=0)
        mock_http.get.return_value = mock_resp

        mock_dir = MagicMock(spec=ScriptDirector)
        mock_dir.analyze.return_value = script

        placeholder = tmp_path / "placeholder.mp4"
        placeholder.write_bytes(b"mp4")
        mock_placeholder = MagicMock(return_value=placeholder)
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", None))

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
            _narration=AsyncMock(return_value=self._track(tmp_path, [5.0])),
            _placeholder=mock_placeholder,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
        )

        assert isinstance(output, VideoOutput)
        mock_placeholder.assert_called_once()

    async def test_generate_renders_ai_scenes_with_stock(self, tmp_path: Path) -> None:
        """RED: AI-flagged scenes are no longer skipped by the stock strategy."""
        ai_scene = SceneOut(
            narration="AI scene.",
            visual_keywords=["quantum"],
            shot_type="close_up",
            duration_seconds=5,
            need_ai_generation=True,
            ai_confidence=0.95,
        )
        stock_scene = SceneOut(
            narration="Stock scene.",
            visual_keywords=["sunset"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(
            scenes=[ai_scene, stock_scene], music_mood="neutral", overall_pace="moderate"
        )

        mock_http = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _pexels_response_json(total_results=1)
        type(mock_resp).content = PropertyMock(return_value=b"data")
        mock_http.get.return_value = mock_resp

        mock_dir = MagicMock(spec=ScriptDirector)
        mock_dir.analyze.return_value = script

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
            _narration=AsyncMock(return_value=self._track(tmp_path, [5.0, 5.0])),
            _placeholder=MagicMock(return_value=tmp_path / "ph.mp4"),
            _compose=MagicMock(return_value=(tmp_path / "final.mp4", None)),
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
        )

        assert isinstance(output, VideoOutput)
        searched = [
            call[1].get("params", {}).get("query", "")
            for call in mock_http.get.call_args_list
            if call[1].get("params")
        ]
        assert any("quantum" in q for q in searched)
        assert any("sunset" in q for q in searched)


class TestStockGeneratorMusic:
    """Background music is resolved from the script mood and forwarded to compose."""

    def _track(self, tmp_path: Path) -> NarrationTrack:
        audio = tmp_path / "voiceover.wav"
        audio.write_bytes(b"wav")
        meta = tmp_path / "voiceover.jsonl"
        meta.write_text("", encoding="utf-8")
        return NarrationTrack(audio_path=audio, metadata_path=meta, durations=[5.0])

    def _selector(self, tmp_path: Path) -> tuple[MagicMock, Path]:
        music_file = tmp_path / "music.mp3"
        music_file.write_bytes(b"m")
        selector = MagicMock(spec=MusicSelector)
        selector.select.return_value = MusicTrack(
            path=music_file, title="T", creator="C", license="cc0", source_url="u"
        )
        return selector, music_file

    async def _run(self, tmp_path: Path, **kwargs: object) -> MagicMock:
        scene = SceneOut(
            narration="A test scene.",
            visual_keywords=["sunset"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(scenes=[scene], music_mood="analytical", overall_pace="moderate")
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", None))
        gen = StockGenerator(
            pexels_api_key="key",
            script_director=MagicMock(),
            _narration=AsyncMock(return_value=self._track(tmp_path)),
            _compose=mock_compose,
            _trim=MagicMock(),
            **kwargs,  # type: ignore[arg-type]
        )
        gen._fetch_scene_clip = MagicMock(return_value=tmp_path / "clip.mp4")  # type: ignore[method-assign]
        await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )
        return mock_compose

    async def test_forwards_music_to_compose(self, tmp_path: Path) -> None:
        """RED: an enabled selector's track is passed to the composer."""
        selector, music_file = self._selector(tmp_path)

        mock_compose = await self._run(tmp_path, music_selector=selector, music_volume=0.25)

        kwargs = mock_compose.call_args.kwargs
        assert kwargs["music_path"] == music_file
        assert kwargs["music_volume"] == 0.25

    async def test_disabled_music_passes_none(self, tmp_path: Path) -> None:
        """RED: music_enabled=False must compose without music."""
        selector, _ = self._selector(tmp_path)

        mock_compose = await self._run(tmp_path, music_selector=selector, music_enabled=False)

        assert mock_compose.call_args.kwargs["music_path"] is None
