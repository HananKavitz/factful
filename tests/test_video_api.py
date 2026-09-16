"""End-to-end API tests for the video render endpoint."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from factful.api.app import create_app
from factful.generation import GenerationRequest
from factful.models import Story
from factful.video.interfaces import VideoOutput
from factful.video.service import VideoService


def _make_client() -> TestClient:
    """Build a test app with mock dependencies."""
    app = create_app(
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "AUTH_MODE": "mock",
            "SESSION_SECRET": "test-secret",
            "LLM_API_KEY": "k",
        }
    )

    # Replace the real VideoService with a mock one
    app.state.video_service = _MockVideoService()

    # Replace the generation runner with a mock that creates stories immediately
    app.state.generation_runner = _make_runner(app)

    return TestClient(app)


def _make_runner(app):
    def runner(record, request: GenerationRequest) -> None:
        with app.state.sessions() as db:
            story = Story(
                user_id=request.user_id,
                prompt=request.prompt,
                angle=request.angle,
                title=f"About {request.prompt}",
                markdown=f"# About {request.prompt}\n\nBody.",
                score=90.0,
                report='{"decision": "publish"}',
            )
            db.add(story)
            db.commit()
            db.refresh(story)
            record.set_story_id(story.id)

    return runner


class _MockVideoService(VideoService):
    """A VideoService that immediately succeeds without calling any external API."""

    def __init__(self, sessions=None) -> None:
        super().__init__(settings=MagicMock(), generators={}, script_director=MagicMock())  # type: ignore[arg-type]
        self._sessions = sessions

    def generate_video(self, *args: object, **kwargs: object) -> VideoOutput:
        return VideoOutput(
            video_path=Path("/fake/output.mp4"),
            subtitle_path=None,
            duration_seconds=30.0,
            resolution="1920x1080",
            file_size_bytes=12345,
        )


def _login(client: TestClient, email: str = "alice@example.com") -> None:
    response = client.post("/api/auth/mock", json={"email": email})
    assert response.status_code == 200


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.01)
    msg = f"job {job_id} did not finish within {timeout}s"
    raise TimeoutError(msg)


def _create_story(client: TestClient) -> int:
    """Create a story (async job) and return its ID once done."""
    response = client.post(
        "/api/stories",
        json={
            "prompt": "test prompt",
            "angle": "test angle",
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    result = _wait_for_job(client, job_id)
    assert result["status"] == "done"
    story_id = result.get("story_id")
    assert story_id is not None
    return story_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVideoEndpoint:
    """Integration tests for the ``POST /api/stories/{id}/render-video`` endpoint."""

    def test_render_video_returns_job_status(self) -> None:
        """RED: submitting a video render request returns a 202 JobStatus."""
        client = _make_client()
        _login(client)
        story_id = _create_story(client)

        response = client.post(f"/api/stories/{story_id}/render-video", json={})
        assert response.status_code == 202

        body = response.json()
        assert "job_id" in body
        assert body["status"] == "queued"

    def test_render_video_job_completes_successfully(self) -> None:
        """RED: the background job should complete with status 'done'."""
        client = _make_client()
        _login(client)
        story_id = _create_story(client)

        response = client.post(f"/api/stories/{story_id}/render-video", json={})
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        result = _wait_for_job(client, job_id)
        assert result["status"] == "done"

    def test_render_video_with_custom_voice(self) -> None:
        """RED: a custom voice parameter is accepted and passed through."""
        client = _make_client()
        _login(client)
        story_id = _create_story(client)

        response = client.post(
            f"/api/stories/{story_id}/render-video",
            json={"voice": "en-GB-SoniaNeural"},
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done"

    def test_render_video_missing_story_returns_404(self) -> None:
        """RED: requesting video for a non-existent story returns 404."""
        client = _make_client()
        _login(client)

        response = client.post("/api/stories/99999/render-video", json={})
        assert response.status_code == 404

    def test_render_video_unauthenticated_returns_401(self) -> None:
        """RED: an unauthenticated request returns 401."""
        client = _make_client()

        response = client.post("/api/stories/1/render-video", json={})
        assert response.status_code == 401

    def test_video_subtitles_endpoint(self) -> None:
        """RED: a completed video job returns status 'done'."""
        client = _make_client()
        _login(client)
        story_id = _create_story(client)

        response = client.post(f"/api/stories/{story_id}/render-video", json={})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done"
        # Subtitles are not generated in the mock
