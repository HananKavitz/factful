"""Tests for the AiGenerator (Kling AI video generation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import uuid4

import httpx
import pytest

from factful.video.exceptions import VideoSourceError
from factful.video.generators.ai import AiGenerator
from factful.video.interfaces import VideoOutput, VideoRequest, VideoScript
from factful.video.script_director import SceneOut

SAMPLE_MARKDOWN = "# AI Topic\n\nQuantum computing."
SAMPLE_TITLE = "AI Topic"


def _kling_response_json(
    *,
    task_id: str | None = None,
    status: str = "succeeded",
    video_url: str = "https://example.com/gen_clip.mp4",
) -> dict[str, Any]:
    tid = task_id or uuid4().hex
    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": tid,
            "status": status,
            "task_status": status,
            "videos": [
                {
                    "id": 1,
                    "url": video_url,
                    "duration": "5s",
                }
            ],
        },
    }


def _kling_submit_response(task_id: str | None = None) -> dict[str, Any]:
    tid = task_id or uuid4().hex
    return {
        "code": 0,
        "message": "success",
        "data": {"task_id": tid},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAiGeneratorName:
    def test_name_returns_ai(self) -> None:
        """RED: the strategy name should be 'ai'."""
        gen = AiGenerator(access_key="key", secret_key="secret")
        assert gen.name() == "ai"


class TestAiGeneratorSubmitTask:
    """Focus on the Kling task submission logic."""

    def test_submit_returns_task_id(self) -> None:
        """RED: a successful submission returns a task ID."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _kling_submit_response(task_id="task_abc")
        mock_client.post.return_value = mock_resp

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        task_id = gen._submit_task("a futuristic quantum computer")
        assert task_id == "task_abc"

    def test_submit_sends_correct_payload(self) -> None:
        """RED: the submission payload should contain the prompt."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _kling_submit_response()
        mock_client.post.return_value = mock_resp

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        gen._submit_task("a neon-lit city at night")
        call_kwargs = mock_client.post.call_args.kwargs or {}
        content_payload = call_kwargs.get("content", b"")
        if isinstance(content_payload, bytes):
            content_payload = content_payload.decode()
        assert "a neon-lit city at night" in content_payload

    def test_submit_error_raises(self) -> None:
        """RED: a non-200 / error response raises VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_client.post.return_value = mock_resp

        gen = AiGenerator(
            access_key="bad",
            secret_key="bad",
            _http_client=mock_client,
        )

        with pytest.raises(VideoSourceError, match="Kling API error"):
            gen._submit_task("anything")

    def test_submit_network_error_raises(self) -> None:
        """RED: a network error during submission raises VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.RequestError("timeout")

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        with pytest.raises(VideoSourceError, match="Kling request failed"):
            gen._submit_task("anything")


class TestAiGeneratorPollTask:
    """Focus on polling for task completion."""

    async def test_poll_returns_video_url_when_done(self) -> None:
        """RED: polling a succeeded task returns the video URL."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _kling_response_json(task_id="task_123", status="succeeded")
        mock_client.get.return_value = mock_resp

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        url = await gen._poll_task("task_123", max_wait_seconds=5, poll_interval_seconds=0.1)
        assert url == "https://example.com/gen_clip.mp4"

    async def test_poll_failed_task_raises(self) -> None:
        """RED: a task that ends in 'failed' status raises VideoSourceError."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = _kling_response_json(task_id="task_123", status="failed")
        mock_client.get.return_value = mock_resp

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        with pytest.raises(VideoSourceError, match="Kling task failed"):
            await gen._poll_task("task_123", max_wait_seconds=5, poll_interval_seconds=0.1)


class TestAiGeneratorDownload:
    def test_download_writes_file(self, tmp_path: Path) -> None:
        """RED: a downloaded clip should be written to the target path."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        type(mock_resp).content = PropertyMock(return_value=b"generated video data")
        mock_client.get.return_value = mock_resp

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
        )

        dest = tmp_path / "gen_clip.mp4"
        result = gen._download_clip("https://example.com/gen_clip.mp4", dest)
        assert result == dest
        assert dest.read_bytes() == b"generated video data"


class TestAiGeneratorGenerate:
    """Full generate() pipeline with mocks."""

    async def test_generate_with_ai_scenes(self, tmp_path: Path) -> None:
        """RED: generates AI clips for scenes needing AI, returns VideoOutput."""
        ai_scene = SceneOut(
            narration="Quantum computers are amazing.",
            visual_keywords=["quantum computer futuristic"],
            shot_type="close_up",
            duration_seconds=5,
            need_ai_generation=True,
            ai_confidence=0.95,
        )
        script = VideoScript(scenes=[ai_scene], music_mood="analytical", overall_pace="moderate")

        # Mock the HTTP client for both submit + poll + download
        mock_client = MagicMock(spec=httpx.Client)
        submit_resp = MagicMock(spec=httpx.Response)
        submit_resp.status_code = 200
        submit_resp.json.return_value = _kling_submit_response(task_id="task_001")

        poll_resp = MagicMock(spec=httpx.Response)
        poll_resp.status_code = 200
        poll_resp.json.return_value = _kling_response_json(task_id="task_001", status="succeeded")

        download_resp = MagicMock(spec=httpx.Response)
        download_resp.status_code = 200
        type(download_resp).content = PropertyMock(return_value=b"gen data")

        mock_client.post.return_value = submit_resp
        mock_client.get.return_value = poll_resp

        # Need to handle 2 GET calls: poll then download
        # Use side_effect for different responses
        mock_client.get.side_effect = [poll_resp, download_resp]

        mock_tts = AsyncMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.wav"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
            _tts=mock_tts,
            _compose=mock_compose,
            _trim=MagicMock(),
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)
        assert output.video_path == tmp_path / "final.mp4"

    async def test_generate_skips_non_ai_scenes(self, tmp_path: Path) -> None:
        """RED: scenes without need_ai_generation are skipped."""
        stock_scene = SceneOut(
            narration="A generic visual.",
            visual_keywords=["nature"],
            shot_type="wide",
            duration_seconds=5,
            need_ai_generation=False,
            ai_confidence=0.0,
        )
        script = VideoScript(scenes=[stock_scene], music_mood="neutral", overall_pace="moderate")

        # If no AI scenes, no Kling API calls should be made
        mock_client = MagicMock(spec=httpx.Client)
        mock_tts = AsyncMock(return_value=(tmp_path / "audio.wav", tmp_path / "meta.wav"))
        mock_compose = MagicMock(return_value=(tmp_path / "final.mp4", tmp_path / "final.vtt"))

        gen = AiGenerator(
            access_key="key",
            secret_key="secret",
            _http_client=mock_client,
            _tts=mock_tts,
            _compose=mock_compose,
        )

        output = await gen.generate(
            VideoRequest(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE),
            tmp_path / "final.mp4",
            script=script,
        )

        assert isinstance(output, VideoOutput)
        mock_client.post.assert_not_called()
        # GET calls: should only be download attempts — none since no AI scenes
        # Actually there will be no clips at all, so no GET calls either
        assert mock_client.get.call_count == 0
