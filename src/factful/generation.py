"""Background generation worker: run the pipeline and persist a Story."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from factful.agents.writer import strip_claim_tags
from factful.config import Settings
from factful.jobstore import JobRecord
from factful.models import Story, Video
from factful.pipeline import DEFAULT_ANGLE, run_pipeline
from factful.progress import ProgressTracker
from factful.report import serialize_report
from factful.runtime import build_runtime
from factful.style.neutral import neutral_profile
from factful.style.schema import StyleProfile
from factful.video import render_video
from factful.video.llm_image_source import LLMImageSource
from factful.video.prompt_generator import PromptGenerator
from factful.video.prompt_validator import PromptValidator
from factful.video.quality_gate import QualityGate
from factful.video.sbert_checker import SBERTRelevanceChecker
from factful.video.settings import VideoSettings as VideoRenderSettings
from factful.video.unsplash import UnsplashSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationRequest:
    user_id: int
    prompt: str
    angle: str | None
    instructions: str | None
    style_profile: StyleProfile | None = None
    temperature: float | None = None
    top_p: float | None = None


GenerationRunner = Callable[[JobRecord, GenerationRequest], None]

VideoRenderer = Callable[[JobRecord, int, str, sessionmaker[Session]], None]


class PipelineCancelledError(Exception):
    """Raised when a generation job is cancelled at a stage boundary."""


def extract_title(markdown: str, fallback: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if next_line and set(next_line) <= {"="} and not stripped.startswith("="):
            return stripped
    return fallback


def run_generation(
    record: JobRecord,
    request: GenerationRequest,
    *,
    sessions: sessionmaker[Session],
    env: Mapping[str, str],
) -> None:
    runtime = build_runtime(dict(env))
    angle = request.angle or DEFAULT_ANGLE
    progress = _cancellable_progress(record, runtime.settings.pipeline.max_passes)
    try:
        result = run_pipeline(
            request.prompt,
            angle,
            settings=runtime.settings,
            searcher=runtime.searcher,
            fetcher=runtime.fetcher,
            clients=runtime.clients,
            profile=request.style_profile or neutral_profile(),
            instructions=request.instructions,
            temperature=request.temperature,
            top_p=request.top_p,
            on_progress=progress,
        )
    except PipelineCancelledError:
        return
    if record.is_cancelled():
        return
    markdown = strip_claim_tags(result.state.draft or "")
    title = result.state.title or ""
    if not title:
        title = (
            request.prompt[:80].rsplit(" ", 1)[0] if len(request.prompt) > 80 else request.prompt
        )
    with sessions() as db:
        story = Story(
            user_id=request.user_id,
            prompt=request.prompt,
            angle=angle,
            instructions=request.instructions,
            title=title,
            markdown=markdown,
            score=result.state.score,
            report=json.dumps(serialize_report(result)),
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        record.set_story_id(story.id)


def build_generation_runner(
    *, sessions: sessionmaker[Session], env: Mapping[str, str]
) -> GenerationRunner:
    def run(record: JobRecord, request: GenerationRequest) -> None:
        run_generation(record, request, sessions=sessions, env=env)

    return run


def _cancellable_progress(record: JobRecord, max_passes: int) -> Callable[[str], None]:
    tracker = ProgressTracker(max_passes=max_passes, on_mark=record.set_progress)

    def set_stage(stage: str) -> None:
        if record.is_cancelled():
            raise PipelineCancelledError()
        tracker.mark()
        record.set_stage(stage)

    return set_stage


def _video_render_progress(
    record: JobRecord,
) -> tuple[Callable[[int, int], None], Callable[[str, float], None]]:
    """Return callbacks mapping video render stages to 0-100% progress.

    Realistic time distribution for video rendering:
       0-2%   initial setup
       2-15%  pre-validation + slide parse (~13%)
      15-28%  per-slide fetching (parallel I/O, ~13%)
      28-38%  composing slides (building clips, ~10%)
      38-95%  FFmpeg encoding (the real bottleneck, ~57%)
      95-100% finalizing / metadata extraction (~5%)
    """

    def on_slide_progress(completed: int, total: int) -> None:
        if total > 0:
            # Slide fetch: 15% → 28%
            pct = 15 + int(13 * completed / total)
            record.set_progress(pct)
            record.set_stage(f"fetching_media ({completed}/{total})")

    def on_compose_progress(stage: str, fraction: float) -> None:
        if stage == "composing":
            # Slide composition: 28% → 38% as each slide is built
            pct = 28 + int(10 * fraction)
            record.set_progress(pct)
            record.set_stage(f"composing ({int(fraction * 100)}%)")
        elif stage == "encoding":
            if fraction == 0.0:
                record.set_stage("encoding video")
                record.set_progress(38)
            elif fraction >= 1.0:
                record.set_progress(95)
                record.set_stage("finalizing")

    return on_slide_progress, on_compose_progress


_VIDEO_DIR = Path(os.environ.get("FACTFUL_VIDEO_DIR", "factful_videos"))


def _build_image_source(
    video_settings: VideoRenderSettings,
    env: Mapping[str, str],
) -> UnsplashSource | LLMImageSource:
    """Build the appropriate image source based on config."""
    if video_settings.image_source_type == "llm":
        return _build_llm_image_source(video_settings, env)
    return _build_unsplash_source(video_settings)


def _build_unsplash_source(video_settings: VideoRenderSettings) -> UnsplashSource:
    """Build an UnsplashSource from video settings."""
    return UnsplashSource(
        api_key=video_settings.unsplash_api_key,
        relevance_mode=video_settings.image_relevance_mode,
    )


def _build_llm_image_source(
    video_settings: VideoRenderSettings,
    env: Mapping[str, str],
) -> LLMImageSource:
    """Build an LLMImageSource with prompt enrichment and quality gate."""
    from factful.llm.client import OpenRouterClient

    base_url = env.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = env.get("LLM_API_KEY", "")

    prompt_client = OpenRouterClient(
        model=video_settings.prompt_model,
        api_key=api_key,
        base_url=base_url,
    )
    prompt_generator = PromptGenerator(client=prompt_client)

    validator = PromptValidator()
    sbert = SBERTRelevanceChecker()
    quality_gate = QualityGate(
        validator=validator,
        sbert=sbert,
        min_semantic_score=video_settings.min_semantic_score,
    )

    return LLMImageSource(
        api_key=api_key,
        prompt_generator=prompt_generator,
        quality_gate=quality_gate,
        image_model=video_settings.image_model,
        regenerate_on_failure=video_settings.regenerate_on_failure,
    )


def run_video_render(
    record: JobRecord,
    story_id: int,
    voice: str,
    *,
    sessions: sessionmaker[Session],
    env: Mapping[str, str],
    settings: Settings,
    video_settings: VideoRenderSettings | None = None,
) -> None:
    """Render a story as a video in a background job."""
    record.set_meta_story_id(story_id)
    record.set_progress(0)
    with sessions() as db:
        story = db.get(Story, story_id)
        if story is None:
            record.set_error(f"story {story_id} not found")
            return

        record.set_stage("preparing")
        record.set_progress(1)
        if video_settings is None:
            video_settings = VideoRenderSettings(
                voice=voice,
                unsplash_api_key=settings.video.unsplash_api_key,
                image_relevance_mode=settings.video.image_relevance_mode,
                fps=settings.video.fps,
                width=settings.video.width,
                height=settings.video.height,
                min_slide_seconds=settings.video.min_slide_seconds,
            )

        image_source = _build_image_source(video_settings, env)

        output_path = _VIDEO_DIR / f"story_{story_id}_{record.id}.mp4"
        slide_progress, compose_progress = _video_render_progress(record)

        record.set_stage("fetching_media")
        record.set_progress(2)

        try:
            render_video(
                markdown=story.markdown,
                title=story.title,
                output_path=output_path,
                image_source=image_source,
                voice=voice,
                settings=video_settings,
                cancel_check=record.is_cancelled,
                on_progress=slide_progress,
                on_compose_progress=compose_progress,
            )
        except Exception as exc:
            error_msg = str(exc)
            video = Video(
                story_id=story_id,
                file_path=str(output_path),
                status="failed",
                voice=voice,
                error_message=error_msg,
            )
            db.add(video)
            db.commit()
            record.set_error(error_msg)
            return

        if record.is_cancelled():
            return

        # Metadata extraction / finalization (95→100%)
        record.set_stage("finalizing")
        record.set_progress(96)

        # Record the completed video
        duration_seconds: float | None = None
        file_size_bytes: int | None = None
        resolution: str | None = None
        if output_path.exists():
            file_size_bytes = output_path.stat().st_size
            try:
                import subprocess

                from factful.video.ffmpeg import ensure_ffmpeg

                ffmpeg = ensure_ffmpeg()
                result = subprocess.run(  # noqa: S603  # trusted path from ensure_ffmpeg()
                    [str(ffmpeg), "-i", str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                # Extract duration from ffprobe-style output
                for line in result.stderr.splitlines():
                    if "Duration:" in line:
                        parts = line.strip().split(",")
                        for part in parts:
                            part = part.strip()
                            if part.startswith("Duration:"):
                                dur_str = part.split(":", 1)[1].strip()
                                h, m, s = dur_str.split(":")
                                duration_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                            elif "x" in part and any(c.isdigit() for c in part):
                                resolution = part.strip()
            except Exception:
                logger.warning("Failed to probe video metadata", exc_info=True)

        video = Video(
            story_id=story_id,
            file_path=str(output_path),
            status="completed",
            voice=voice,
            duration_seconds=duration_seconds,
            file_size_bytes=file_size_bytes,
            resolution=resolution,
        )
        db.add(video)
        db.commit()

        # Mark the job done so the frontend stops polling
        record.set_story_id(story_id)


def build_video_renderer(
    *,
    sessions: sessionmaker[Session],
    env: Mapping[str, str],
    settings: Settings,
    video_settings: VideoRenderSettings | None = None,
) -> VideoRenderer:
    def run(record: JobRecord, story_id: int, voice: str, sessions: sessionmaker[Session]) -> None:
        run_video_render(
            record,
            story_id,
            voice,
            sessions=sessions,
            env=env,
            settings=settings,
            video_settings=video_settings,
        )

    return run
