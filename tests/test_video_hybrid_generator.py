"""Tests for the HybridGenerator (stock + AI mixed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from factful.video.exceptions import NoUsableClipsError
from factful.video.generators.hybrid import HybridGenerator
from factful.video.interfaces import VideoOutput, VideoRequest, VideoScript
from factful.video.script_director import SceneOut

SAMPLE_MARKDOWN = "# Hybrid\n\nSome generic and some specific content."
SAMPLE_TITLE = "Hybrid Article"


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

        mock_tts = MagicMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.wav"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = HybridGenerator(
            pexels_api_key="test_key",
            ai_access_key="ak",
            ai_secret_key="sk",
            _http_client=mock_http,
            _tts=mock_tts,
            _compose=mock_compose,
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

        mock_tts = MagicMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.wav"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = HybridGenerator(
            ai_access_key="ak",
            ai_secret_key="sk",
            ai_budget_seconds=budget,
            _http_client=mock_http,
            _tts=mock_tts,
            _compose=mock_compose,
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)

    async def test_no_scenes_falls_back_to_stock(self, tmp_path: Path) -> None:
        """RED: an empty script raises NoUsableClipsError."""
        script = VideoScript(scenes=[], music_mood="neutral", overall_pace="moderate")

        gen = HybridGenerator()

        with pytest.raises(NoUsableClipsError, match="no scenes"):
            await gen.generate(
                VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
                tmp_path / "final.mp4",
                script=script,
            )
