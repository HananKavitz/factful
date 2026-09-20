"""AiGenerator: generates AI video clips via Kling API for each scene.

Strategy name: ``ai``

This generator:
1. Runs the Script Director (if no pre-computed script is provided).
2. For each scene with ``need_ai_generation=True``, submits a text-to-video
   generation task to Kling, polls for completion, and downloads the result.
3. Scenes that don't need AI generation are skipped.
4. Generates TTS voiceover and composes the final video via moviepy.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from factful.video.composer import (
    compose_final_video,
    make_placeholder_clip,
    trim_or_loop_clip,
)
from factful.video.exceptions import (
    CompositionError,
    NoUsableClipsError,
    VideoSourceError,
)
from factful.video.interfaces import (
    VideoGenerator,
    VideoOutput,
    VideoRequest,
    VideoScript,
)
from factful.video.narration import synthesize_narration
from factful.video.script_director import ScriptDirector

logger = logging.getLogger(__name__)

_KLING_BASE_URL = "https://api.klingai.com"
_KLING_TEXT2VIDEO_PATH = "/v1/videos/text2video"
_DEFAULT_POLL_INTERVAL = 3.0
_DEFAULT_MAX_WAIT = 300.0


def _kling_sign(
    method: str,
    path: str,
    body: str,
    access_key: str,
    secret_key: str,
    timestamp: str,
) -> str:
    """Generate HMAC-SHA256 signature for Kling API authentication."""
    msg = f"{method}\n{path}\n{timestamp}\n{body}"
    sig = hmac.new(
        secret_key.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"AK={access_key}:{sig}"


class AiGenerator(VideoGenerator):
    """Generate AI video clips via Kling and compose a full video.

    Args:
        access_key: Kling API access key.
        secret_key: Kling API secret key.
        script_director: ``ScriptDirector`` instance for markdown→script.
        width: Output video width (default 1920).
        height: Output video height (default 1080).
        fps: Output frame rate (default 30).
        voice: Default TTS voice.
        tts_rate: TTS rate string.
        tts_pitch: TTS pitch string.
        model: Kling model name.
        clip_duration_seconds: Duration per AI-generated clip.
        _http_client: Optional injected ``httpx.Client`` (for tests).
        _narration: Optional injected narration synthesizer (for tests).
        _placeholder: Optional injected placeholder maker (for tests).
        _compose: Optional injected compose callable (for tests).
        _trim: Optional injected clip trim/loop callable (for tests).
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        script_director: ScriptDirector | None = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        voice: str = "en-US-AriaNeural",
        tts_rate: str = "-15%",
        tts_pitch: str = "-5Hz",
        model: str = "kling/kling-1.6",
        clip_duration_seconds: int = 5,
        _http_client: httpx.Client | None = None,
        _narration: Callable[..., Any] | None = None,
        _placeholder: Callable[..., Any] | None = None,
        _compose: Callable[..., Any] | None = None,
        _trim: Callable[..., Any] | None = None,
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._director = script_director
        self._width = width
        self._height = height
        self._fps = fps
        self._voice = voice
        self._tts_rate = tts_rate
        self._tts_pitch = tts_pitch
        self._model = model
        self._clip_duration = clip_duration_seconds
        self._http_client = _http_client or httpx.Client(timeout=60.0)
        self._narration = _narration or synthesize_narration
        self._placeholder = _placeholder or make_placeholder_clip
        self._compose = _compose or compose_final_video
        self._trim = _trim or trim_or_loop_clip

    # ------------------------------------------------------------------
    # VideoGenerator protocol
    # ------------------------------------------------------------------

    def name(self) -> str:
        """Return the strategy name."""
        return "ai"

    async def generate(
        self,
        request: VideoRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        script: VideoScript | None = None,
    ) -> VideoOutput:
        """Run the full AI-video pipeline.

        1. Script Director (if needed)
        2. Per-scene narration (measured durations)
        3. One Kling clip per scene (retry, then placeholder), sized to narration
        4. Compose final video
        """
        if on_progress is not None:
            on_progress("script_director", 0.0)

        # Step 1: Script Director
        if script is None and self._director is not None:
            script = self._director.analyze(markdown=request.markdown, title=request.title)

        if not script or not script.scenes:
            raise NoUsableClipsError("Script Director returned no scenes")

        workdir = output_path.parent / f".ai_{uuid.uuid4().hex[:8]}"
        workdir.mkdir(parents=True, exist_ok=True)
        voice = request.voice or self._voice

        # Step 2: narration — measured durations drive clip lengths
        if on_progress is not None:
            on_progress("tts", 0.0)
        narration = await self._narration(
            script.scenes,
            workdir,
            voice=voice,
            rate=self._tts_rate,
            pitch=self._tts_pitch,
            on_progress=(lambda f: on_progress("tts", f)) if on_progress is not None else None,
        )

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # Step 3: one AI clip per scene, trimmed to the narrated duration
        if on_progress is not None:
            on_progress("generating_clips", 0.0)

        clip_paths: list[Path] = []
        total_scenes = len(script.scenes)

        for idx, scene in enumerate(script.scenes):
            if cancel_check and cancel_check():
                return VideoOutput(video_path=output_path)

            if on_progress is not None:
                on_progress("generating_clips", (idx + 1) / total_scenes)

            clip_paths.append(
                await self._fetch_scene_clip(
                    scene,
                    idx,
                    workdir,
                    narration.durations[idx],
                    cancel_check=cancel_check,
                )
            )

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # Step 4: Compose final video
        if on_progress is not None:
            on_progress("composing", 0.0)

        try:
            video_path, subtitle_path = self._compose(
                clip_paths=clip_paths,
                audio_path=narration.audio_path,
                output_path=output_path,
                metadata_path=narration.metadata_path,
                narration_text=narration.narration_text,
                width=self._width,
                height=self._height,
                fps=self._fps,
                cancel_check=cancel_check,
                on_progress=on_progress,
            )
        except CompositionError:
            logger.error("Video composition failed")
            raise

        if on_progress is not None:
            on_progress("finalizing", 1.0)

        stat = video_path.stat() if video_path.exists() else None

        return VideoOutput(
            video_path=video_path,
            subtitle_path=subtitle_path,
            duration_seconds=None,
            resolution=f"{self._width}x{self._height}",
            file_size_bytes=stat.st_size if stat else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_scene_clip(
        self,
        scene: Any,
        idx: int,
        workdir: Path,
        duration: float,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Path:
        """Generate and trim one AI clip for a scene, or a placeholder on failure."""
        prompt = " ".join(scene.visual_keywords) if scene.visual_keywords else ""
        if not prompt:
            prompt = scene.narration[:200]

        if prompt:
            video_url = await self._try_generate(prompt, duration, cancel_check=cancel_check)
            if video_url is not None:
                clip_dest = workdir / f"scene_{idx:04d}.mp4"
                try:
                    self._download_clip(video_url, clip_dest)
                    trimmed = workdir / f"scene_{idx:04d}_trimmed.mp4"
                    try:
                        return self._trim(clip_dest, duration, trimmed)
                    except CompositionError:
                        logger.warning(
                            "Failed to trim/loop AI clip for scene %d, using raw clip", idx
                        )
                        return clip_dest
                except VideoSourceError:
                    logger.warning("Failed to download Kling clip for scene %d", idx)

        logger.info("No AI clip for scene %d — using placeholder", idx)
        return self._placeholder(
            duration,
            workdir / f"scene_{idx:04d}_placeholder.mp4",
            width=self._width,
            height=self._height,
            fps=self._fps,
        )

    async def _try_generate(
        self,
        prompt: str,
        duration: float,
        *,
        cancel_check: Callable[[], bool] | None = None,
        attempts: int = 2,
    ) -> str | None:
        """Submit and poll a Kling task, retrying once before giving up."""
        kling_duration = min(self._clip_duration, max(2, round(duration)))
        for attempt in range(1, attempts + 1):
            try:
                task_id = self._submit_task(prompt, duration=kling_duration)
                return await self._poll_task(task_id, cancel_check=cancel_check)
            except VideoSourceError as exc:
                logger.warning(
                    "Kling attempt %d/%d failed for prompt '%s': %s",
                    attempt,
                    attempts,
                    prompt,
                    exc,
                )
        return None

    def _auth_headers(self, *, method: str, path: str, body: str = "") -> dict[str, str]:
        """Build Kling API authentication headers for any method/path."""
        ts = str(int(time.time()))
        signature = _kling_sign(
            method=method,
            path=path,
            body=body,
            access_key=self._access_key,
            secret_key=self._secret_key,
            timestamp=ts,
        )
        headers: dict[str, str] = {
            "Authorization": signature,
            "Timestamp": ts,
        }
        if method == "POST":
            headers["Content-Type"] = "application/json"
        return headers

    def _submit_task(self, prompt: str, duration: int | None = None) -> str:
        """Submit a text-to-video generation task to Kling.

        Args:
            prompt: The text prompt for video generation.
            duration: Desired clip duration in seconds. Falls back to
                ``self._clip_duration`` when not provided.

        Returns:
            The task ID for polling.

        Raises:
            VideoSourceError: on API or network error.
        """
        body_dict: dict[str, Any] = {
            "model_name": self._model,
            "prompt": prompt,
            "duration": duration if duration is not None else self._clip_duration,
            "cfg": 0.5,
            "mode": "pro",
        }
        body_str = json.dumps(body_dict, separators=(",", ":"))

        try:
            response = self._http_client.post(
                f"{_KLING_BASE_URL}{_KLING_TEXT2VIDEO_PATH}",
                headers=self._auth_headers(
                    method="POST", path=_KLING_TEXT2VIDEO_PATH, body=body_str
                ),
                content=body_str,
            )
        except httpx.RequestError as exc:
            raise VideoSourceError(f"Kling request failed: {exc}") from exc

        if response.status_code != 200:
            raise VideoSourceError(f"Kling API error (HTTP {response.status_code})")

        try:
            data = response.json()
        except Exception as exc:
            raise VideoSourceError(f"Kling submit returned invalid JSON: {exc}") from exc

        if data.get("code") != 0:
            raise VideoSourceError(f"Kling API error: {data.get('message', 'unknown')}")

        task_id: str | None = data.get("data", {}).get("task_id")
        if not task_id:
            raise VideoSourceError("Kling did not return a task ID")

        return task_id

    async def _poll_task(
        self,
        task_id: str,
        max_wait_seconds: float = _DEFAULT_MAX_WAIT,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL,
        cancel_check: Callable[[], bool] | None = None,
    ) -> str:
        """Poll a Kling task until it completes or fails.

        Args:
            task_id: The Kling task ID to poll.
            max_wait_seconds: Maximum total wait time.
            poll_interval_seconds: Time between polls.
            cancel_check: Returns True if the job was cancelled.

        Returns:
            The URL of the generated video.

        Raises:
            VideoSourceError: on failure, timeout, or cancellation.
        """
        poll_path = f"{_KLING_TEXT2VIDEO_PATH}/{task_id}"
        deadline = time.monotonic() + max_wait_seconds

        while time.monotonic() < deadline:
            if cancel_check is not None and cancel_check():
                raise VideoSourceError("Kling polling cancelled")

            try:
                response = self._http_client.get(
                    f"{_KLING_BASE_URL}{poll_path}",
                    headers=self._auth_headers(method="GET", path=poll_path, body=""),
                )
            except httpx.RequestError as exc:
                raise VideoSourceError(f"Kling poll request failed: {exc}") from exc

            if response.status_code != 200:
                raise VideoSourceError(f"Kling poll error (HTTP {response.status_code})")

            try:
                data = response.json()
            except Exception as exc:
                raise VideoSourceError(f"Kling poll returned invalid JSON: {exc}") from exc

            task_status = data.get("data", {}).get("task_status", "")

            if task_status == "succeeded":
                videos: list[dict[str, Any]] = data.get("data", {}).get("videos", [])
                if videos and videos[0].get("url"):
                    url: str = videos[0]["url"]
                    return url
                raise VideoSourceError("Kling task succeeded but no video URL returned")

            if task_status in ("failed", "error"):
                raise VideoSourceError(f"Kling task failed (status: {task_status})")

            # Still processing — wait and retry
            await asyncio.sleep(poll_interval_seconds)

        raise VideoSourceError(f"Kling task {task_id} did not complete within {max_wait_seconds}s")

    def _download_clip(self, url: str, dest: Path) -> Path:
        """Download a generated video clip to disk.

        Raises:
            VideoSourceError: on network or I/O failure.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self._http_client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        except (httpx.RequestError, OSError) as exc:
            raise VideoSourceError(f"failed to download AI clip from {url}: {exc}") from exc
        return dest
