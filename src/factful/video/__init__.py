"""Video rendering pipeline: convert a markdown story into an MP4 slideshow video."""

from __future__ import annotations

import concurrent.futures
import shutil
from collections.abc import Callable
from pathlib import Path

from factful.video.composer import compose_video
from factful.video.exceptions import VideoRenderError, ImageSourceError, TTSError
from factful.video.ffmpeg import ensure_ffmpeg
from factful.video.settings import VideoSettings
from factful.video.slides import parse_slides
from factful.video.sources import ImageSource
from factful.video.tts import generate_speech


def _tts_heading(slide_index: int, heading: str, title: str) -> str:
    """Return a TTS-friendly heading, stripping LLM instructions and long text."""
    if slide_index == 0:
        return title
    cleaned = heading.split(".")[0].split("\n")[0].strip()
    if len(cleaned) > 100:
        cleaned = cleaned[:100].rsplit(" ", 1)[0] + "..."
    return cleaned


def _render_slide(
    slide_index: int,
    slide_heading: str,
    slide_body_lines: list[str],
    title: str,
    voice: str,
    work_dir: Path,
    image_source: ImageSource,
) -> tuple[Path, Path]:
    """Fetch image and generate TTS for one slide (called in parallel)."""
    img_path = work_dir / f"slide_{slide_index:03d}.jpg"
    image_source.fetch(
        heading=slide_heading,
        body=" ".join(slide_body_lines),
        output_path=img_path,
    )

    tts_text = _tts_heading(slide_index, slide_heading, title)
    text_parts = [tts_text] + slide_body_lines
    speech_text = " — ".join(p for p in text_parts if p)
    audio_path = work_dir / f"slide_{slide_index:03d}.wav"
    generate_speech(speech_text, output_path=audio_path, voice=voice)

    return img_path, audio_path


def render_video(
    markdown: str,
    title: str,
    output_path: Path,
    image_source: ImageSource,
    voice: str = "en-US-AriaNeural",
    *,
    settings: VideoSettings | None = None,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_compose_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Render a markdown story to an MP4 slideshow video.

    Images and TTS are fetched in parallel across slides for speed.

    Args:
        markdown: The story content in markdown.
        title: The story title (used for the intro slide when no headings).
        output_path: Where to write the output MP4.
        image_source: Pluggable image provider (e.g. UnsplashSource).
        voice: edge-tts voice name.
        settings: Video rendering settings (defaults used if None).
        cancel_check: Optional callable returning True if the job was cancelled.
        on_progress: Optional callback invoked as (completed_slides, total_slides)
            as each slide's image/TTS fetch completes.
        on_compose_progress: Optional callback invoked as (stage, fraction)
            during slide composition and video encoding.

    Returns:
        output_path on success.

    Raises:
        VideoRenderError: if the markdown is empty, FFmpeg is missing,
            or any image/tts step fails.
    """
    if not markdown or not markdown.strip():
        raise VideoRenderError("cannot render video from empty markdown")

    resolved = settings or VideoSettings()
    ensure_ffmpeg()

    slides = parse_slides(markdown, title=title)
    if not slides:
        raise VideoRenderError("cannot render video from empty markdown")

    # Pre-validation: check every slide's image source before any expensive work
    errors: list[tuple[int, str]] = []
    for i, slide in enumerate(slides):
        msg = image_source.validate(heading=slide.heading, body=" ".join(slide.body_lines))
        if msg is not None:
            errors.append((i, msg))
    if errors:
        details = "; ".join(f"slide {i + 1} ('{slides[i].heading}'): {msg}" for i, msg in errors)
        raise VideoRenderError(f"Image source unavailable for {len(errors)} slide(s): {details}")

    if cancel_check and cancel_check():
        return output_path

    work_dir = output_path.parent / f".{output_path.stem}_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Parallel fetch: download all images and generate all TTS concurrently
        image_paths: list[Path] = [None] * len(slides)  # type: ignore[list-item]
        audio_paths: list[Path] = [None] * len(slides)  # type: ignore[list-item]
        max_workers = min(resolved.max_concurrent_fetches, len(slides))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures: dict[concurrent.futures.Future[tuple[Path, Path]], int] = {}
            for i, slide in enumerate(slides):
                if cancel_check and cancel_check():
                    return output_path
                future = pool.submit(
                    _render_slide,
                    i,
                    slide.heading,
                    slide.body_lines,
                    title,
                    voice,
                    work_dir,
                    image_source,
                )
                futures[future] = i

            completed = 0
            total = len(slides)
            for future in concurrent.futures.as_completed(futures):
                if cancel_check and cancel_check():
                    return output_path
                idx = futures[future]
                try:
                    img_path, audio_path = future.result()
                    image_paths[idx] = img_path
                    audio_paths[idx] = audio_path
                except (ImageSourceError, TTSError, OSError) as exc:
                    raise VideoRenderError(
                        f"slide {idx + 1} ('{slides[idx].heading}') failed: {exc}"
                    ) from exc
                completed += 1
                if on_progress is not None:
                    on_progress(completed, total)

        if cancel_check and cancel_check():
            return output_path

        # Compose the final video
        output_path.parent.mkdir(parents=True, exist_ok=True)
        compose_video(
            slides=slides,
            image_paths=[p for p in image_paths if p is not None],
            audio_paths=[p for p in audio_paths if p is not None],
            output_path=output_path,
            settings=resolved,
            cancel_check=cancel_check,
            on_progress=on_compose_progress,
        )
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)

    return output_path
