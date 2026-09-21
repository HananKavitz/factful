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
from factful.video.generators.ai import AiGenerator
from factful.video.generators.stock import (
    DEFAULT_MAX_RANK_CANDIDATES,
    MAX_DOWNLOAD_ATTEMPTS,
    PEXELS_PER_PAGE,
    build_pexels_query,
    order_pexels_candidates,
    preferred_candidates,
)
from factful.video.interfaces import (
    Scene,
    VideoGenerator,
    VideoOutput,
    VideoRequest,
    VideoScript,
)
from factful.video.music import MusicSelector, select_music
from factful.video.narration import synthesize_narration
from factful.video.rankers import ClipRanker, NoOpRanker, PexelsCandidate
from factful.video.script_director import ScriptDirector

logger = logging.getLogger(__name__)

_PEXELS_API_URL = "https://api.pexels.com/videos/search"


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
        _narration: Optional injected narration synthesizer (for tests).
        _placeholder: Optional injected placeholder maker (for tests).
        _compose: Optional injected compose callable (for tests).
        _trim: Optional injected clip trim/loop callable (for tests).
        ranker: Clip ranker for Pexels results (default: keep Pexels order).
        clip_rank_max_candidates: How many Pexels results to send to the ranker.
        music_selector: Optional background-music selector (Openverse, CC0).
        music_enabled: Whether to add background music at all.
        music_volume: Background-music gain (0.0-1.0).
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
        _narration: Callable[..., Any] | None = None,
        _placeholder: Callable[..., Any] | None = None,
        _compose: Callable[..., Any] | None = None,
        _trim: Callable[..., Any] | None = None,
        ranker: ClipRanker | None = None,
        clip_rank_max_candidates: int = DEFAULT_MAX_RANK_CANDIDATES,
        music_selector: MusicSelector | None = None,
        music_enabled: bool = True,
        music_volume: float = 0.15,
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
        self._narration = _narration or synthesize_narration
        self._placeholder = _placeholder or make_placeholder_clip
        self._compose = _compose or compose_final_video
        self._trim = _trim or trim_or_loop_clip
        self._ranker = ranker or NoOpRanker()
        self._clip_rank_max_candidates = clip_rank_max_candidates
        self._music_selector = music_selector
        self._music_enabled = music_enabled
        self._music_volume = music_volume

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
        """Run the full hybrid pipeline.

        1. Script Director (if needed)
        2. Per-scene narration (measured durations)
        3. AI clip (if flagged & within budget) else stock, then placeholder
        4. Compose final video
        """
        if on_progress is not None:
            on_progress("script_director", 0.0)

        if script is None and self._director is not None:
            script = self._director.analyze(markdown=request.markdown, title=request.title)

        if not script or not script.scenes:
            raise NoUsableClipsError("Script Director returned no scenes")

        workdir = output_path.parent / f".hybrid_{uuid.uuid4().hex[:8]}"
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

        # Step 3: one visual per scene, trimmed to the narrated duration
        if on_progress is not None:
            on_progress("fetching_clips", 0.0)

        clip_paths: list[Path] = []
        used_ids: set[int] = set()
        used_narration_words: set[str] = set()
        remaining_ai_budget: float = float(self._ai_budget)
        total_scenes = len(script.scenes)

        for idx, scene in enumerate(script.scenes):
            if cancel_check and cancel_check():
                return VideoOutput(video_path=output_path)

            if on_progress is not None:
                on_progress("fetching_clips", (idx + 1) / total_scenes)

            duration = narration.durations[idx]
            clip_path: Path | None = None

            if scene.need_ai_generation and remaining_ai_budget >= duration:
                clip_path = await self._try_fetch_ai_clip(
                    scene, idx, workdir, duration, cancel_check=cancel_check
                )
                if clip_path is not None:
                    remaining_ai_budget -= duration

            if clip_path is None:
                clip_path = self._try_fetch_stock_clip(
                    scene,
                    idx,
                    workdir,
                    duration,
                    used_ids,
                    used_narration_words,
                    request.title,
                )

            if clip_path is None:
                logger.info("No visual for scene %d — using placeholder", idx)
                clip_path = self._placeholder(
                    duration,
                    workdir / f"scene_{idx:04d}_placeholder.mp4",
                    width=self._width,
                    height=self._height,
                    fps=self._fps,
                )

            clip_paths.append(clip_path)

        if cancel_check and cancel_check():
            return VideoOutput(video_path=output_path)

        # Step 4: Compose final video
        if on_progress is not None:
            on_progress("composing", 0.0)

        music_path = select_music(
            self._music_selector,
            enabled=self._music_enabled,
            mood=script.music_mood,
            dest_dir=workdir,
        )

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
                music_path=music_path,
                music_volume=self._music_volume,
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
        scene: Scene,
        idx: int,
        workdir: Path,
        duration: float,
        used_ids: set[int],
        used_narration_words: set[str],
        title: str = "",
    ) -> Path | None:
        """Search Pexels for a scene and download the best clip.

        Args:
            scene: A scene object with visual_keywords and narration.
            idx: Scene index (used for filenames and logging).
            workdir: Directory for downloaded clips.
            duration: Target duration (measured narration), in seconds.
            used_ids: Set of already-used Pexels video ids (updated in-place).
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
            candidates = self._search_pexels(query)
        except VideoSourceError:
            logger.warning("Pexels search failed for '%s'", query)
            return None

        ranked = self._ranker.rank(scene, candidates[: self._clip_rank_max_candidates])
        if not ranked:
            logger.info("No acceptable Pexels result for '%s'", query)
            return None

        # Dedup by video id; reuse the best match if every candidate was used.
        dest = workdir / f"stock_{idx:04d}.mp4"
        downloaded = False
        attempts = 0
        for candidate in preferred_candidates(ranked, used_ids):
            if candidate.video_id is not None:
                used_ids.add(candidate.video_id)
            for url in candidate.links:
                if attempts >= MAX_DOWNLOAD_ATTEMPTS:
                    break
                attempts += 1
                try:
                    self._download_clip(url, dest)
                    downloaded = True
                    break
                except VideoSourceError:
                    logger.warning("Failed to download stock clip for scene %d from %s", idx, url)
            if downloaded:
                break

        if not downloaded:
            return None

        trimmed = workdir / f"stock_{idx:04d}_trimmed.mp4"
        try:
            dest = self._trim(dest, duration, trimmed)
        except CompositionError:
            logger.warning("Failed to trim/loop stock clip for scene %d, using raw clip", idx)

        return dest

    async def _try_fetch_ai_clip(
        self,
        scene: object,
        idx: int,
        workdir: Path,
        duration: float,
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

        video_url = await ai_gen._try_generate(prompt, duration, cancel_check=cancel_check)
        if video_url is None:
            logger.warning("Kling generation failed for '%s'", prompt)
            return None

        dest = workdir / f"ai_{idx:04d}.mp4"
        try:
            self._download_clip(video_url, dest)
        except VideoSourceError:
            logger.warning("Failed to download AI clip for scene %d", idx)
            return None

        trimmed = workdir / f"ai_{idx:04d}_trimmed.mp4"
        try:
            dest = self._trim(dest, duration, trimmed)
        except CompositionError:
            logger.warning("Failed to trim/loop AI clip for scene %d, using raw clip", idx)

        return dest

    def _search_pexels(self, query: str) -> list[PexelsCandidate]:
        """Search page 1 of Pexels for stock video candidates.

        Args:
            query: Search query string.

        Returns candidates in Pexels relevance order, each with ranked links.
        """
        params: dict[str, Any] = {
            "query": query,
            "per_page": PEXELS_PER_PAGE,
            "page": 1,
            "orientation": "landscape",
            "size": "medium",
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

        return order_pexels_candidates(videos)

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
