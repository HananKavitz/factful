"""VideoService: orchestrates the full video generation pipeline.

The service wires together the Script Director, a selected generator
strategy (stock, ai, hybrid), TTS, and the composer, and persists the
result to a ``Video`` database record.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from factful.llm.client import OpenRouterClient
from factful.models import Story, Video
from factful.video.exceptions import VideoGenerationError
from factful.video.generators.ai import AiGenerator
from factful.video.generators.hybrid import HybridGenerator
from factful.video.generators.stock import StockGenerator
from factful.video.interfaces import (
    VideoGenerator,
    VideoOutput,
    VideoRequest,
    VideoScript,
)
from factful.video.music import MusicSelector
from factful.video.rankers import ClipRanker, LlmVisionRanker, NoOpRanker
from factful.video.script_director import ScriptDirector
from factful.video.settings import VideoSettings

logger = logging.getLogger(__name__)


def _write_script(script: VideoScript, directory: Path) -> Path:
    """Persist the generated script to the video directory as JSON.

    Written next to the rendered MP4 so the script that drove a video can
    be inspected later (e.g. to verify every narration segment is covered
    by a scene).

    Args:
        script: The ``VideoScript`` produced by the Script Director.
        directory: The video output directory.

    Returns:
        The path of the written ``script.json`` file.
    """
    script_path = directory / "script.json"
    script_path.write_text(
        json.dumps(asdict(script), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return script_path


def build_video_service(
    *,
    settings: VideoSettings,
    env: Mapping[str, str],
    llm_api_key: str,
    llm_base_url: str,
) -> VideoService:
    """Factory: create a VideoService from settings and environment.

    Args:
        settings: ``VideoSettings`` from ``config/settings.yaml``.
        env: Environment variables (for API keys).
        llm_api_key: API key for the Script Director's LLM.
        llm_base_url: Base URL for the LLM API.

    Returns:
        A configured ``VideoService``.
    """
    # Build the Script Director's LLM client
    llm_client = OpenRouterClient(
        model=settings.script_director_model,
        api_key=llm_api_key,
        base_url=llm_base_url,
    )
    script_director = ScriptDirector(client=llm_client, max_scenes=settings.max_scenes)

    # Build the Pexels clip ranker
    ranker: ClipRanker
    if settings.clip_rank_mode == "llm_vision":
        ranker = LlmVisionRanker(
            client=OpenRouterClient(
                model=settings.clip_rank_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
            ),
            min_score=settings.clip_rank_min_score,
        )
    else:
        ranker = NoOpRanker()

    # Build the background-music selector (Openverse, CC0, anonymous)
    music_selector = MusicSelector(
        license_id=settings.music_license,
        min_duration_seconds=settings.music_min_duration_seconds,
        max_duration_seconds=settings.music_max_duration_seconds,
        max_candidates=settings.music_max_candidates,
    )

    # Build the stock generator
    pexels_api_key = env.get(settings.stock_api_key_env, "")
    stock_generator = StockGenerator(
        pexels_api_key=pexels_api_key,
        script_director=script_director,
        width=settings.width,
        height=settings.height,
        fps=settings.fps,
        voice=settings.voice,
        tts_rate=settings.tts_rate,
        tts_pitch=settings.tts_pitch,
        ranker=ranker,
        clip_rank_max_candidates=settings.clip_rank_max_candidates,
        music_selector=music_selector,
        music_enabled=settings.music_enabled,
        music_volume=settings.music_volume,
    )

    # Build the AI generator
    kling_access_key = env.get(settings.ai_api_key_env + "_ACCESS_KEY", "")
    kling_secret_key = env.get(settings.ai_api_key_env + "_SECRET_KEY", "")
    ai_generator = AiGenerator(
        access_key=kling_access_key,
        secret_key=kling_secret_key,
        script_director=script_director,
        width=settings.width,
        height=settings.height,
        fps=settings.fps,
        voice=settings.voice,
        tts_rate=settings.tts_rate,
        tts_pitch=settings.tts_pitch,
        model=settings.ai_model,
        clip_duration_seconds=settings.ai_clip_duration_seconds,
        music_selector=music_selector,
        music_enabled=settings.music_enabled,
        music_volume=settings.music_volume,
    )

    # Build the hybrid generator
    hybrid_generator = HybridGenerator(
        script_director=script_director,
        pexels_api_key=pexels_api_key,
        ai_access_key=kling_access_key,
        ai_secret_key=kling_secret_key,
        width=settings.width,
        height=settings.height,
        fps=settings.fps,
        voice=settings.voice,
        tts_rate=settings.tts_rate,
        tts_pitch=settings.tts_pitch,
        ai_budget_seconds=settings.hybrid_ai_budget_seconds,
        model=settings.ai_model,
        clip_duration_seconds=settings.ai_clip_duration_seconds,
        ranker=ranker,
        clip_rank_max_candidates=settings.clip_rank_max_candidates,
        music_selector=music_selector,
        music_enabled=settings.music_enabled,
        music_volume=settings.music_volume,
    )

    # Registry of available strategies
    generators: dict[str, VideoGenerator] = {
        "stock": stock_generator,
        "ai": ai_generator,
        "hybrid": hybrid_generator,
    }

    return VideoService(
        settings=settings,
        generators=generators,
        script_director=script_director,
    )


class VideoService:
    """Orchestrates video generation from article → MP4.

    Wires together the Script Director, a generator strategy (stock, ai,
    hybrid), and persists the result to the database.
    """

    def __init__(
        self,
        *,
        settings: VideoSettings,
        generators: dict[str, VideoGenerator],
        script_director: ScriptDirector,
    ) -> None:
        self._settings = settings
        self._generators = generators
        self._director = script_director

    def generate_video(
        self,
        story: Story,
        voice: str,
        sessions: sessionmaker[Session],
        *,
        strategy: str | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> VideoOutput:
        """Run the full video generation pipeline synchronously.

        This method is designed to be called from a background job
        (``JobStore`` thread pool). It wraps the async generator call
        with ``asyncio.run()``.

        Args:
            story: The ``Story`` ORM model to render.
            voice: TTS voice name.
            sessions: SQLAlchemy session factory.
            strategy: Generator strategy name (defaults to ``default_strategy``).
            on_progress: Optional (stage, fraction) callback.
            cancel_check: Optional callable returning True if cancelled.

        Returns:
            The ``VideoOutput`` from the generator.

        Raises:
            VideoGenerationError: on any pipeline failure.
        """
        strategy_name = strategy or self._settings.default_strategy
        generator = self._generators.get(strategy_name)
        if generator is None:
            raise VideoGenerationError(
                f"Unknown video strategy: {strategy_name!r}. Available: {list(self._generators)}"
            )

        request = VideoRequest(
            markdown=story.markdown or "",
            title=story.title or "",
            voice=voice,
        )

        # Determine output path before running (so we can create the Video record)
        output_dir = Path("videos") / str(story.id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "final.mp4"

        # Create the Video DB record
        with sessions() as db:
            video_record = Video(
                story_id=story.id,
                file_path=str(output_path),
                status="running",
                voice=voice,
            )
            db.add(video_record)
            db.commit()
            db.refresh(video_record)
            video_id = video_record.id

        try:
            # Run the Script Director once here so the script can be saved
            # and shared with the generator instead of being discarded.
            if on_progress is not None:
                on_progress("script_director", 0.0)
            script = self._director.analyze(
                markdown=story.markdown or "",
                title=story.title or "",
            )
            _write_script(script, output_dir)

            # Run the async generator
            output = asyncio.run(
                generator.generate(
                    request,
                    output_path,
                    cancel_check=cancel_check,
                    on_progress=on_progress,
                    script=script,
                )
            )
        except VideoGenerationError:
            logger.exception("Video generation failed for story %d", story.id)
            with sessions() as db:
                vid = db.get(Video, video_id)
                if vid is not None:
                    vid.status = "failed"
                    vid.error_message = "Video generation failed"
                    db.commit()
            raise
        except Exception:
            logger.exception("Unexpected video generation error for story %d", story.id)
            with sessions() as db:
                vid = db.get(Video, video_id)
                if vid is not None:
                    vid.status = "failed"
                    vid.error_message = "Unexpected error"
                    db.commit()
            raise

        # Update the Video record with successful results
        with sessions() as db:
            vid = db.get(Video, video_id)
            if vid is not None:
                vid.status = "completed"
                vid.file_path = str(output.video_path)
                vid.duration_seconds = output.duration_seconds
                vid.file_size_bytes = output.file_size_bytes
                vid.resolution = output.resolution
                vid.subtitle_path = str(output.subtitle_path) if output.subtitle_path else None
                db.commit()

        return output
