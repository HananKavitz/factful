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
        assert all(u.startswith("https://") for u in urls)

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
        assert params.get("query") == "city skyline"
        assert params.get("per_page") == 15
        assert params.get("orientation") == "landscape"
        assert params.get("size") == "large"

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


# ---------------------------------------------------------------------------
# Integration-style: full generate() with all mocks
# ---------------------------------------------------------------------------


class TestStockGeneratorGenerate:
    """End-to-end generate() with all collaborators mocked."""

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

        mock_tts = AsyncMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.jsonl"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
            _tts=mock_tts,
            _compose=mock_compose,
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

    async def test_generate_no_clips_fetched_raises(self, tmp_path: Path) -> None:
        """RED: when Pexels returns no results for any scene, NoUsableClipsError is raised."""
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

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
        )

        with pytest.raises(NoUsableClipsError, match="Could not fetch any stock video clips"):
            await gen.generate(
                VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
                tmp_path / "final.mp4",
            )

    async def test_generate_skips_ai_scenes(self, tmp_path: Path) -> None:
        """RED: scenes needing AI generation are skipped, not searched."""
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

        mock_tts = AsyncMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.wav"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = StockGenerator(
            pexels_api_key="key",
            script_director=mock_dir,
            _http_client=mock_http,
            _tts=mock_tts,
            _compose=mock_compose,
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
        )

        assert isinstance(output, VideoOutput)
        # First call is search (with params), second is download (no params)
        assert mock_http.get.call_count == 2
        search_call = mock_http.get.call_args_list[0]
        search_params = search_call[1].get("params", {})
        assert search_params.get("query") == "sunset"
        # No search was made for "quantum" (AI scene was skipped)
        for call in mock_http.get.call_args_list:
            params = call[1].get("params", {})
            assert params.get("query") != "quantum"
