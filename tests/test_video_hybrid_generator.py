"""Tests for the HybridGenerator (stock + AI mixed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from factful.video.exceptions import NoUsableClipsError
from factful.video.generators.hybrid import HybridGenerator
from factful.video.interfaces import VideoOutput, VideoRequest, VideoScript
from factful.video.music import MusicSelector, MusicTrack
from factful.video.narration import NarrationTrack
from factful.video.script_director import SceneOut

SAMPLE_MARKDOWN = "# Hybrid\n\nSome generic and some specific content."
SAMPLE_TITLE = "Hybrid Article"


def _track(tmp_path: Path, durations: list[float]) -> NarrationTrack:
    audio = tmp_path / "voiceover.wav"
    audio.write_bytes(b"wav")
    meta = tmp_path / "voiceover.jsonl"
    meta.write_text("", encoding="utf-8")
    return NarrationTrack(audio_path=audio, metadata_path=meta, durations=durations)


def _pexels_response(*, total: int = 1) -> dict[str, Any]:
    return {
        "total_results": total,
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
                        "link": f"https://example.com/stock{i}.mp4",
                    }
                ],
            }
            for i in range(total)
        ],
    }


def _kling_submit_response(task_id: str = "task_001") -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": {"task_id": task_id}}


def _kling_poll_response(url: str = "https://example.com/ai_clip.mp4") -> dict[str, Any]:
    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": "task_001",
            "task_status": "succeeded",
            "videos": [{"id": 1, "url": url, "duration": "5s"}],
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHybridGeneratorName:
    def test_name_returns_hybrid(self) -> None:
        """RED: the strategy name should be 'hybrid'."""
        gen = HybridGenerator()
        assert gen.name() == "hybrid"


class TestHybridGeneratorGenerate:
    """End-to-end hybrid pipeline with both generators mocked."""

    async def test_stock_for_normal_ai_for_specific(self, tmp_path: Path) -> None:
        """RED: normal scenes use stock, AI-required scenes use Kling."""
        normal = SceneOut(
            narration="A beautiful sunset.",
            visual_keywords=["sunset"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        specific = SceneOut(
            narration="Quantum entanglement explained.",
            visual_keywords=["quantum entanglement abstract"],
            shot_type="close_up",
            duration_seconds=5,
            need_ai_generation=True,
            ai_confidence=0.95,
        )
        script = VideoScript(
            scenes=[normal, specific],
            music_mood="analytical",
            overall_pace="moderate",
        )

        # Build HTTP mocks for stock search + download + AI submit/poll/download
        mock_http = MagicMock(spec=httpx.Client)

        # Pexels search response
        pexels_resp = MagicMock(spec=httpx.Response)
        pexels_resp.status_code = 200
        pexels_resp.json.return_value = _pexels_response(total=1)

        # Kling submit response
        kling_submit = MagicMock(spec=httpx.Response)
        kling_submit.status_code = 200
        kling_submit.json.return_value = _kling_submit_response()

        # Kling poll response
        kling_poll = MagicMock(spec=httpx.Response)
        kling_poll.status_code = 200
        kling_poll.json.return_value = _kling_poll_response()

        # Download responses (no spec — content is a property on httpx.Response)
        stock_dl = MagicMock()
        stock_dl.status_code = 200
        stock_dl.content = b"stock data"

        ai_dl = MagicMock()
        ai_dl.status_code = 200
        ai_dl.content = b"ai data"

        # Wire responses: stock search (GET), stock dl (GET), kling poll (GET), ai dl (GET)
        mock_http.get.side_effect = [pexels_resp, stock_dl, kling_poll, ai_dl]
        mock_http.post.return_value = kling_submit

        mock_narration = AsyncMock(return_value=_track(tmp_path, [5.0, 5.0]))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = HybridGenerator(
            pexels_api_key="test_key",
            ai_access_key="ak",
            ai_secret_key="sk",
            _http_client=mock_http,
            _narration=mock_narration,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)

    async def test_ai_budget_respected(self, tmp_path: Path) -> None:
        """RED: AI scenes are limited by ai_budget_seconds."""
        many_ai_scenes = [
            SceneOut(
                narration=f"Specific concept {i}.",
                visual_keywords=[f"concept_{i}"],
                shot_type="close_up",
                duration_seconds=10,
                need_ai_generation=True,
                ai_confidence=0.95,
            )
            for i in range(6)
        ]
        script = VideoScript(
            scenes=many_ai_scenes, music_mood="analytical", overall_pace="moderate"
        )

        # With a budget of 30 seconds and each scene needing 10s, only 3 AI clips
        budget = 30

        mock_http = MagicMock(spec=httpx.Client)

        # Return success for everything
        submit_resp = MagicMock(spec=httpx.Response)
        submit_resp.status_code = 200
        submit_resp.json.return_value = _kling_submit_response()

        poll_resp = MagicMock(spec=httpx.Response)
        poll_resp.status_code = 200
        poll_resp.json.return_value = _kling_poll_response()

        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.content = b"data"

        # 3 Kling submits (POST), 3 polls (GET), 3 downloads (GET) = 6 GETs + 3 POSTs
        mock_http.post.return_value = submit_resp
        mock_http.get.side_effect = [poll_resp, dl_resp, poll_resp, dl_resp, poll_resp, dl_resp] * 3

        mock_narration = AsyncMock(return_value=_track(tmp_path, [10.0] * 6))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))
        placeholder = tmp_path / "placeholder.mp4"
        placeholder.write_bytes(b"mp4")
        mock_placeholder = MagicMock(return_value=placeholder)

        gen = HybridGenerator(
            ai_access_key="ak",
            ai_secret_key="sk",
            ai_budget_seconds=budget,
            _http_client=mock_http,
            _narration=mock_narration,
            _placeholder=mock_placeholder,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)
        # Budget of 30s / 10s per scene → at most 3 Kling submissions.
        assert mock_http.post.call_count == 3
        # The three over-budget scenes fall back to hermetic placeholders.
        assert mock_placeholder.call_count == 3

    async def test_placeholder_when_stock_and_ai_fail(self, tmp_path: Path) -> None:
        """RED: a scene with no stock and no AI still gets a placeholder."""
        scene = SceneOut(
            narration="Specific concept.",
            visual_keywords=["concept"],
            shot_type="close_up",
            duration_seconds=5,
            need_ai_generation=True,
            ai_confidence=0.95,
        )
        script = VideoScript(scenes=[scene], music_mood="analytical", overall_pace="moderate")

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.post.side_effect = httpx.RequestError("offline")
        # Pexels search returns nothing → no download.
        pexels_resp = MagicMock(spec=httpx.Response)
        pexels_resp.status_code = 200
        pexels_resp.json.return_value = _pexels_response(total=0)
        mock_http.get.return_value = pexels_resp

        placeholder = tmp_path / "placeholder.mp4"
        placeholder.write_bytes(b"mp4")
        mock_placeholder = MagicMock(return_value=placeholder)
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", None))

        gen = HybridGenerator(
            pexels_api_key="k",
            ai_access_key="ak",
            ai_secret_key="sk",
            _http_client=mock_http,
            _narration=AsyncMock(return_value=_track(tmp_path, [8.0])),
            _placeholder=mock_placeholder,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)
        assert mock_placeholder.call_args.args[0] == 8.0

    async def test_no_scenes_raises(self, tmp_path: Path) -> None:
        """RED: an empty script raises NoUsableClipsError."""
        script = VideoScript(scenes=[], music_mood="neutral", overall_pace="moderate")

        gen = HybridGenerator()

        with pytest.raises(NoUsableClipsError, match="no scenes"):
            await gen.generate(
                VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
                tmp_path / "final.mp4",
                script=script,
            )


class TestHybridPexelsOrder:
    """The hybrid generator shares the relevance-preserving Pexels ordering."""

    def test_search_preserves_pexels_relevance_order(self) -> None:
        """RED: hybrid keeps Pexels video order instead of re-sorting by size."""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "total_results": 2,
            "videos": [
                {
                    "id": 1,
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
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = search_resp

        gen = HybridGenerator(pexels_api_key="k", _http_client=mock_http)

        urls = gen._search_pexels("x")
        assert urls[0].link == "https://example.com/top_hit.mp4"
        assert urls[1].link == "https://example.com/less_relevant.mp4"


class TestHybridStockRanker:
    """A ranker rejection routes the hybrid scene away from stock."""

    def test_ranker_rejection_returns_none(self, tmp_path: Path) -> None:
        """RED: when no candidate is acceptable, hybrid skips the stock clip."""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.status_code = 200
        search_resp.json.return_value = _pexels_response(total=1)
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.return_value = search_resp

        ranker = MagicMock()
        ranker.rank.return_value = []
        gen = HybridGenerator(
            pexels_api_key="k",
            _http_client=mock_http,
            _trim=MagicMock(),
            ranker=ranker,
        )
        scene = SceneOut(
            narration="Unrelated concept.",
            visual_keywords=["concept"],
            shot_type="close_up",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )

        result = gen._try_fetch_stock_clip(scene, 0, tmp_path, 5.0, set(), set(), "Title")

        assert result is None
        assert mock_http.get.call_count == 1  # search only, no download


class TestHybridStockRetry:
    """Stock fallback retries the next candidate when a download fails."""

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

        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.content = b"clip"

        def _get(url: str, *args: Any, **kwargs: Any) -> Any:
            if "search" in url:
                return search_resp
            if url.endswith("/bad.mp4"):
                raise httpx.RequestError("timeout")
            return good_resp

        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = _get

        trimmed = tmp_path / "stock_0000_trimmed.mp4"
        gen = HybridGenerator(
            pexels_api_key="k",
            _http_client=mock_http,
            _trim=MagicMock(return_value=trimmed),
        )
        scene = SceneOut(
            narration="Ocean waves crash on the shore.",
            visual_keywords=["ocean"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )

        result = gen._try_fetch_stock_clip(scene, 0, tmp_path, 5.0, set(), set(), "Title")

        assert result == trimmed


class TestHybridGeneratorMusic:
    """Background music is resolved from the script mood and forwarded to compose."""

    async def test_forwards_music_to_compose(self, tmp_path: Path) -> None:
        """RED: an enabled selector's track is passed to the composer."""
        scene = SceneOut(
            narration="A beautiful sunset.",
            visual_keywords=["sunset"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(scenes=[scene], music_mood="calm", overall_pace="moderate")

        music_file = tmp_path / "music.mp3"
        music_file.write_bytes(b"m")
        selector = MagicMock(spec=MusicSelector)
        selector.select.return_value = MusicTrack(
            path=music_file, title="T", creator="C", license="cc0", source_url="u"
        )
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", None))

        gen = HybridGenerator(
            _narration=AsyncMock(return_value=_track(tmp_path, [5.0])),
            _compose=mock_compose,
            _trim=MagicMock(),
            music_selector=selector,
            music_volume=0.2,
        )
        gen._try_fetch_stock_clip = MagicMock(return_value=tmp_path / "clip.mp4")  # type: ignore[method-assign]

        await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        kwargs = mock_compose.call_args.kwargs
        assert kwargs["music_path"] == music_file
        assert kwargs["music_volume"] == 0.2
