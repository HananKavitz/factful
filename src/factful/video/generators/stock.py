"""StockGenerator: fetches stock video clips from Pexels for each scene.

Strategy name: ``stock``

This generator:
1. Runs the Script Director (if no pre-computed script is provided).
2. For each scene with ``need_ai_generation=False``, searches Pexels for a
   matching stock clip and downloads the highest-resolution result.
3. Scenes that require AI generation are skipped (fallback: a black placeholder).
4. Generates TTS voiceover and composes the final video via moviepy.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from factful.video.composer import compose_final_video
from factful.video.exceptions import (
    CompositionError,
    NoUsableClipsError,
    TTSGenerationError,
    VideoSourceError,
)
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
_DEFAULT_PER_PAGE = 15
_DEFAULT_ORIENTATION = "landscape"
_DEFAULT_SIZE = "large"
_DEFAULT_MIN_RESOLUTION_PIXELS = 1920 * 1080  # 1080p


def _pixel_count(video: dict[str, Any]) -> int:
    return (video.get("width") or 0) * (video.get("height") or 0)


class StockGenerator(VideoGenerator):
    """Fetch stock video clips from Pexels and compose a full video.

    Args:
        pexels_api_key: Pexels API key.
        script_director: ``ScriptDirector`` instance for markdown→script.
        width: Output video width (default 1920).
        height: Output video height (default 1080).
        fps: Output frame rate (default 30).
        voice: Default TTS voice.
        tts_rate: TTS rate string.
        tts_pitch: TTS pitch string.
        _http_client: Optional injected ``httpx.Client`` (for tests).
        _tts: Optional injected TTS callable (for tests).
        _compose: Optional injected compose callable (for tests).
    """

    def __init__(
        self,
        pexels_api_key: str,
        script_director: ScriptDirector,
        *,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        voice: str = "en-US-AriaNeural",
        tts_rate: str = "-15%",
        tts_pitch: str = "-5Hz",
        _http_client: httpx.Client | None = None,
        _tts: Callable[..., Any] | None = None,
        _compose: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = pexels_api_key
        self._director = script_director
        self._width = width
        self._height = height
        self._fps = fps
        self._voice = voice
        self._tts_rate = tts_rate
        self._tts_pitch = tts_pitch
        self._http_client = _http_client or httpx.Client(timeout=30.0)
        self._tts = _tts or generate_speech
        self._compose = _compose or compose_final_video

    # ------------------------------------------------------------------
    # VideoGenerator protocol
    # ------------------------------------------------------------------

    def name(self) -> str:
        """Return the strategy name."""
        return "stock"

    async def generate(
        self,
        request: VideoRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        script: VideoScript | None = None,
    ) -> VideoOutput:
        """Run the full stock-video pipeline.

        1. Script Director (if needed)
        2. Search & download Pexels clips
        3. TTS voiceover
        4. Compose final video
        """
        if on_progress is not None:
            on_progress("script_director", 0.0)

        # Step 1: Script Director
        if script is None:
            script = self._director.analyze(markdown=request.markdown, title=request.title)

        if not script.scenes:
            raise NoUsableClipsError("Script Director returned no scenes")

        # Step 2: Search & download Pexels clips
        if on_progress is not None:
            on_progress("fetching_clips", 0.0)

        clip_paths: list[Path] = []
        workdir = output_path.parent / f".stock_{uuid.uuid4().hex[:8]}"
        workdir.mkdir(parents=True, exist_ok=True)

        total_scenes = len(script.scenes)
        for idx, scene in enumerate(script.scenes):
            if cancel_check and cancel_check():
                return VideoOutput(video_path=output_path)

            if on_progress is not None:
                on_progress("fetching_clips", (idx + 1) / total_scenes)

            logger.info(
                "Scene %d/%d: need_ai=%s, kw=%s",
                idx + 1, total_scenes, scene.need_ai_generation, scene.visual_keywords,
            )

            if scene.need_ai_generation:
                logger.info(
                    "Skipping scene %d (needs AI generation) — no stock clip",
                    idx,
                )
                continue

            query = " ".join(scene.visual_keywords) if scene.visual_keywords else ""
            if not query:
                logger.info("Skipping scene %d — no visual keywords", idx)
                continue

            try:
                urls = self._search_pexels(query, min_results=1)
                logger.info("Pexels returned %d URLs for '%s'", len(urls), query)
            except VideoSourceError as e:
                logger.warning("Pexels search failed for '%s': %s", query, e)
                continue

            if not urls:
                logger.info("No Pexels results for query '%s'", query)
                continue

            clip_dest = workdir / f"scene_{idx:04d}.mp4"
            try:
                self._download_clip(urls[0], clip_dest)
            except VideoSourceError:
                logger.warning("Failed to download clip for scene %d", idx)
                continue

            clip_paths.append(clip_dest)
            logger.info("Downloaded clip %s (%d bytes)", clip_dest.name, clip_dest.stat().st_size)

        logger.info("Total clips fetched: %d", len(clip_paths))
        if not clip_paths:
            logger.error("No usable stock clips were fetched")
            raise NoUsableClipsError("Could not fetch any stock video clips from Pexels")

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # Step 3: TTS
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

        # Step 4: Compose final video
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

        # Build VideoOutput from the final file
        stat = video_path.stat() if video_path.exists() else None

        return VideoOutput(
            video_path=video_path,
            subtitle_path=subtitle_path,
            duration_seconds=None,  # not measured
            resolution=f"{self._width}x{self._height}",
            file_size_bytes=stat.st_size if stat else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_pexels(self, query: str, min_results: int = 1) -> list[str]:
        """Search Pexels for stock video clips.

        Returns a list of download URLs sorted by quality (best first).
        """
        params: dict[str, Any] = {
            "query": query,
            "per_page": _DEFAULT_PER_PAGE,
            "orientation": _DEFAULT_ORIENTATION,
            "size": _DEFAULT_SIZE,
        }

        try:
            response = self._http_client.get(
                _PEXELS_API_URL,
                params=params,
                headers={"Authorization": self._api_key},
            )
        except httpx.RequestError as exc:
            raise VideoSourceError(f"Pexels request failed: {exc}") from exc

        if response.status_code != 200:
            raise VideoSourceError(f"Pexels API error (HTTP {response.status_code})")

        data = response.json()
        videos: list[dict[str, Any]] = data.get("videos", [])
        if not videos:
            return []

        # Collect all HD video files across all results
        candidates: list[dict[str, Any]] = []
        for video in videos:
            for vf in video.get("video_files", []):
                w = vf.get("width") or 0
                h = vf.get("height") or 0
                if w * h >= _DEFAULT_MIN_RESOLUTION_PIXELS:
                    candidates.append(
                        {
                            "width": w,
                            "height": h,
                            "link": vf["link"],
                        }
                    )

        if not candidates:
            # Fall back to any available files
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

        # Sort: highest pixel count first
        candidates.sort(key=_pixel_count, reverse=True)
        return [c["link"] for c in candidates]

    def _select_best_clip(self, videos: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Return the video file dict with the highest pixel count."""
        if not videos:
            return None
        return max(videos, key=_pixel_count)

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
