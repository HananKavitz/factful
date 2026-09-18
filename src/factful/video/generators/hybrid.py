"""HybridGenerator: mixes Pexels stock footage + Kling AI clips.

Strategy name: ``hybrid``

This generator:
1. Runs the Script Director (if no pre-computed script is provided).
2. For each scene with ``need_ai_generation=False``, searches Pexels for a
   matching stock clip.
3. For each scene with ``need_ai_generation=True``, submits a text-to-video
   generation task to Kling, subject to ``ai_budget_seconds``.
4. Generates TTS voiceover and composes the final video via moviepy.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from factful.video.composer import compose_final_video, trim_or_loop_clip
from factful.video.exceptions import (
    CompositionError,
    NoUsableClipsError,
    TTSGenerationError,
    VideoSourceError,
)
from factful.video.generators.ai import AiGenerator
from factful.video.generators.stock import build_pexels_query
from factful.video.interfaces import (
    VideoGenerator,
    VideoOutput,
    VideoRequest,
    VideoScript,
)
from factful.video.script_director import ScriptDirector
from factful.video.tts import generate_speech

logger = logging.getLogger(__name__)

_PEXELS_API_URL = "https://api.pexels.com/videos/search"


def _pixel_count(video: dict[str, Any]) -> int:
    return (video.get("width") or 0) * (video.get("height") or 0)


class HybridGenerator(VideoGenerator):
    """Mix stock footage and AI-generated clips for the final video.

    Args:
        stock_generator: Pre-configured StockGenerator for Pexels searches.
        ai_generator: Pre-configured AiGenerator for Kling generation.
        script_director: ``ScriptDirector`` for markdown→script.
        pexels_api_key: Pexels API key (fallback if stock_generator not provided).
        ai_access_key: Kling access key (fallback).
        ai_secret_key: Kling secret key (fallback).
        width: Output video width.
        height: Output video height.
        fps: Output frame rate.
        voice: Default TTS voice.
        tts_rate: TTS rate string.
        tts_pitch: TTS pitch string.
        ai_budget_seconds: Maximum total seconds of AI-generated video.
        _http_client: Optional injected ``httpx.Client`` (for tests).
        _tts: Optional injected TTS callable (for tests).
        _compose: Optional injected compose callable (for tests).
        _trim: Optional injected clip trim/loop callable (for tests).
    """

    def __init__(
        self,
        *,
        script_director: ScriptDirector | None = None,
        pexels_api_key: str = "",
        ai_access_key: str = "",
        ai_secret_key: str = "",
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        voice: str = "en-US-AriaNeural",
        tts_rate: str = "-15%",
        tts_pitch: str = "-5Hz",
        ai_budget_seconds: int = 30,
        model: str = "kling/kling-1.6",
        clip_duration_seconds: int = 5,
        _http_client: httpx.Client | None = None,
        _tts: Callable[..., Any] | None = None,
        _compose: Callable[..., Any] | None = None,
        _trim: Callable[..., Any] | None = None,
    ) -> None:
        self._director = script_director
        self._pexels_api_key = pexels_api_key
        self._ai_access_key = ai_access_key
        self._ai_secret_key = ai_secret_key
        self._width = width
        self._height = height
        self._fps = fps
        self._voice = voice
        self._tts_rate = tts_rate
        self._tts_pitch = tts_pitch
        self._ai_budget = ai_budget_seconds
        self._model = model
        self._clip_duration = clip_duration_seconds
        self._http_client = _http_client or httpx.Client(timeout=30.0)
        self._tts = _tts or generate_speech
        self._compose = _compose or compose_final_video
        self._trim = _trim or trim_or_loop_clip

    # ------------------------------------------------------------------
    # VideoGenerator protocol
    # ------------------------------------------------------------------

    def name(self) -> str:
        return "hybrid"

    async def generate(
        self,
        request: VideoRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        script: VideoScript | None = None,
    ) -> VideoOutput:
        if on_progress is not None:
            on_progress("script_director", 0.0)

        if script is None and self._director is not None:
            script = self._director.analyze(markdown=request.markdown, title=request.title)

        if not script or not script.scenes:
            raise NoUsableClipsError("Script Director returned no scenes")

        if on_progress is not None:
            on_progress("fetching_clips", 0.0)

        clip_paths: list[Path] = []
        used_urls: set[str] = set()
        used_narration_words: set[str] = set()
        workdir = output_path.parent / f".hybrid_{uuid.uuid4().hex[:8]}"
        workdir.mkdir(parents=True, exist_ok=True)

        remaining_ai_budget = self._ai_budget
        total_scenes = len(script.scenes)

        for idx, scene in enumerate(script.scenes):
            if cancel_check and cancel_check():
                return VideoOutput(video_path=output_path)

            if on_progress is not None:
                on_progress("fetching_clips", (idx + 1) / total_scenes)

            if scene.need_ai_generation and remaining_ai_budget >= scene.duration_seconds:
                # Use AI generation
                clip_path = await self._try_fetch_ai_clip(
                    scene, idx, workdir, remaining_ai_budget, cancel_check=cancel_check
                )
                if clip_path:
                    clip_paths.append(clip_path)
                    remaining_ai_budget -= scene.duration_seconds
                continue

            # Use stock footage (fallback for AI scenes over budget too)
            if not scene.need_ai_generation or remaining_ai_budget < scene.duration_seconds:
                clip_path = self._try_fetch_stock_clip(
                    scene,
                    idx,
                    workdir,
                    used_urls,
                    used_narration_words,
                    request.title,
                )
                if clip_path:
                    clip_paths.append(clip_path)
                continue

        if not clip_paths:
            raise NoUsableClipsError("Could not fetch any video clips from stock or AI sources")

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # TTS
        if on_progress is not None:
            on_progress("tts", 0.0)

        voice = request.voice or self._voice
        full_text = "\n".join(s.narration for s in script.scenes if s.narration)
        audio_path = workdir / "voiceover.wav"

        try:
            audio_path, metadata_path = await self._tts(
                full_text,
                audio_path,
                voice=voice,
                rate=self._tts_rate,
                pitch=self._tts_pitch,
            )
        except TTSGenerationError:
            logger.error("TTS generation failed")
            raise

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # Compose
        if on_progress is not None:
            on_progress("composing", 0.0)

        try:
            video_path, subtitle_path = self._compose(
                clip_paths=clip_paths,
                audio_path=audio_path,
                output_path=output_path,
                metadata_path=metadata_path,
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

    def _try_fetch_stock_clip(
        self,
        scene: object,
        idx: int,
        workdir: Path,
        used_urls: set[str],
        used_narration_words: set[str],
        title: str = "",
    ) -> Path | None:
        """Search Pexels for a scene and download the best clip.

        Args:
            scene: A scene object with visual_keywords and narration.
            idx: Scene index (used for pagination).
            workdir: Directory for downloaded clips.
            used_urls: Set of already-downloaded URLs (deduplicated in-place).
            used_narration_words: Set of narration words already used in
                earlier scenes (deduplicated in-place).
            title: Article title (prepended for topical relevance).

        Returns the clip path, or None on failure.
        """
        keywords = getattr(scene, "visual_keywords", [])
        narration = getattr(scene, "narration", "")
        query = build_pexels_query(keywords, narration, title, used_narration_words)
        if not query:
            return None

        try:
            urls = self._search_pexels(query, page=idx + 1)
        except VideoSourceError:
            logger.warning("Pexels search failed for '%s'", query)
            return None

        if not urls:
            logger.info("No Pexels results for '%s'", query)
            return None

        # Skip already-used URLs; pick the first fresh one
        fresh_url = next((u for u in urls if u not in used_urls), None)
        if fresh_url is None:
            logger.info("All Pexels results for '%s' already used — skipping", query)
            return None

        used_urls.add(fresh_url)

        dest = workdir / f"stock_{idx:04d}.mp4"
        try:
            self._download_clip(fresh_url, dest)
        except VideoSourceError:
            logger.warning("Failed to download stock clip for scene %d", idx)
            return None

        # Trim or loop the stock clip to match the scene's intended duration
        trimmed = workdir / f"stock_{idx:04d}_trimmed.mp4"
        scene_dur = getattr(scene, "duration_seconds", 8)
        try:
            dest = self._trim(dest, scene_dur, trimmed)
        except CompositionError:
            logger.warning("Failed to trim/loop stock clip for scene %d, using raw clip", idx)

        return dest

    async def _try_fetch_ai_clip(
        self,
        scene: object,
        idx: int,
        workdir: Path,
        budget_remaining: int,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Path | None:
        """Generate an AI clip for a scene and download it.

        Returns the clip path, or None on failure.
        """
        keywords = getattr(scene, "visual_keywords", [])
        narration = getattr(scene, "narration", "")
        prompt = " ".join(keywords) if keywords else narration[:200]
        if not prompt:
            return None

        # Lazy-init the internal AI generator with full config
        ai_gen = AiGenerator(
            access_key=self._ai_access_key,
            secret_key=self._ai_secret_key,
            model=self._model,
            clip_duration_seconds=self._clip_duration,
            _http_client=self._http_client,
        )

        try:
            task_id = ai_gen._submit_task(prompt)
            video_url = await ai_gen._poll_task(task_id, cancel_check=cancel_check)
        except VideoSourceError:
            logger.warning("Kling generation failed for '%s'", prompt)
            return None

        dest = workdir / f"ai_{idx:04d}.mp4"
        try:
            self._download_clip(video_url, dest)
        except VideoSourceError:
            logger.warning("Failed to download AI clip for scene %d", idx)
            return None

        # Trim or loop the AI clip to match the scene's intended duration
        trimmed = workdir / f"ai_{idx:04d}_trimmed.mp4"
        scene_dur = getattr(scene, "duration_seconds", 8)
        try:
            dest = self._trim(dest, scene_dur, trimmed)
        except CompositionError:
            logger.warning("Failed to trim/loop AI clip for scene %d, using raw clip", idx)

        return dest

    def _search_pexels(self, query: str, page: int = 1) -> list[str]:
        """Search Pexels for stock video clips matching the query.

        Args:
            query: Search query string.
            page: Pexels result page (used to rotate results per scene).

        Returns a list of download URLs sorted by quality (best first).
        """
        params: dict[str, Any] = {
            "query": query,
            "per_page": 5,
            "page": page,
            "orientation": "landscape",
            "size": "large",
        }

        try:
            response = self._http_client.get(
                _PEXELS_API_URL,
                params=params,
                headers={"Authorization": self._pexels_api_key},
            )
        except httpx.RequestError as exc:
            raise VideoSourceError(f"Pexels request failed: {exc}") from exc

        if response.status_code != 200:
            raise VideoSourceError(f"Pexels API error (HTTP {response.status_code})")

        data = response.json()
        videos: list[dict[str, Any]] = data.get("videos", [])
        if not videos:
            return []

        candidates: list[dict[str, Any]] = []
        for video in videos:
            for vf in video.get("video_files", []):
                w = vf.get("width") or 0
                h = vf.get("height") or 0
                if w * h >= 1920 * 1080 and vf.get("link"):
                    candidates.append({"width": w, "height": h, "link": vf["link"]})

        if not candidates:
            for video in videos:
                for vf in video.get("video_files", []):
                    if vf.get("link"):
                        candidates.append(
                            {
                                "width": vf.get("width") or 0,
                                "height": vf.get("height") or 0,
                                "link": vf["link"],
                            }
                        )

        candidates.sort(key=_pixel_count, reverse=True)
        return [c["link"] for c in candidates]

    def _download_clip(self, url: str, dest: Path) -> Path:
        """Download a single video clip to disk.

        Raises:
            VideoSourceError: on network or I/O failure.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self._http_client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        except (httpx.RequestError, OSError) as exc:
            raise VideoSourceError(f"failed to download clip from {url}: {exc}") from exc
        return dest
