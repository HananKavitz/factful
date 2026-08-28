"""Video composition using moviepy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from factful.video.exceptions import CompositionError
from factful.video.ffmpeg import ensure_ffmpeg
from factful.video.settings import VideoSettings
from factful.video.slides import Slide


def compose_video(
    slides: list[Slide],
    image_paths: list[Path],
    audio_paths: list[Path],
    output_path: Path,
    settings: VideoSettings,
    *,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Composite slides, images, and audio into a single MP4 video.

    Each slide gets a background image with overlaid captions and audio.
    Slides are concatenated with crossfade transitions.

    Args:
        slides: The slide deck (for caption text).
        image_paths: Background image for each slide (same length as slides).
        audio_paths: TTS audio for each slide (same length as slides).
        output_path: Where to write the final MP4.
        settings: Video rendering parameters.
        cancel_check: Optional cancellation check between slides.
        on_progress: Optional callback invoked as (stage, fraction) where
            stage is "composing" or "encoding" and fraction is 0.0–1.0.

    Returns:
        output_path on success.

    Raises:
        CompositionError: if composition fails or inputs are invalid.
    """
    if not slides:
        raise CompositionError("cannot compose video from empty slide list")
    if len(slides) != len(image_paths):
        raise CompositionError(
            f"slide count ({len(slides)}) does not match image count ({len(image_paths)})"
        )
    if len(slides) != len(audio_paths):
        raise CompositionError(
            f"slide count ({len(slides)}) does not match audio count ({len(audio_paths)})"
        )

    # Ensure FFmpeg is available before starting composition
    ensure_ffmpeg()

    try:
        from moviepy import (
            AudioClip,
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_audioclips,
            concatenate_videoclips,
        )
    except ImportError as exc:
        raise CompositionError("moviepy is not installed") from exc

    if cancel_check and cancel_check():
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        clips: list[CompositeVideoClip] = []
        total_slides = len(slides)
        for i, slide in enumerate(slides):
            if cancel_check and cancel_check():
                return output_path

            # Report composing progress for each slide building
            if on_progress is not None:
                on_progress("composing", (i + 1) / total_slides)

            # Background image clip
            img_clip = ImageClip(str(image_paths[i]))
            img_clip = img_clip.resized((settings.width, settings.height))

            # Audio — for the first slide, pre-pend 4 seconds of silence
            # so the title has a moment before the narration begins.
            audio = AudioFileClip(str(audio_paths[i]))
            if i == 0:
                silence = AudioClip(lambda t: 0, duration=4.0, fps=audio.fps)
                audio = concatenate_audioclips([silence, audio])
            duration = max(audio.duration, settings.min_slide_seconds)

            # Caption text — heading on first line, then body below
            heading_line = slide.heading or ""
            body_text = "\n".join(slide.body_lines) if slide.body_lines else ""
            caption_lines = [h for h in [heading_line] if h] + ([body_text] if body_text else [])
            caption_text = "\n\n".join(caption_lines)
            txt_clip = _make_caption_clip(
                text=caption_text,
                duration=duration,
                width=settings.width,
                height=settings.height,
            )

            # Composite: image + text overlay + audio
            composite = CompositeVideoClip(
                [img_clip, txt_clip] if txt_clip else [img_clip],
                size=(settings.width, settings.height),
            )
            composite = composite.with_duration(duration)
            composite = composite.with_audio(audio)
            clips.append(composite)

        if not clips:
            raise CompositionError("no video clips were created")

        if on_progress is not None:
            on_progress("encoding", 0.0)

        # Concatenate with crossfade
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(
            str(output_path),
            fps=settings.fps,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            bitrate="1000k",
            temp_audiofile=str(output_path.parent / f".{output_path.stem}_audio.m4a"),
            remove_temp=True,
            logger=None,
        )

        if on_progress is not None:
            on_progress("encoding", 1.0)

    except Exception as exc:
        raise CompositionError(f"video composition failed: {exc}") from exc

    if not output_path.exists():
        raise CompositionError(f"output file was not created at {output_path}")

    return output_path


def _make_caption_clip(
    text: str,
    duration: float,
    width: int,
    height: int,
) -> object | None:
    """Create a TextClip for slide captions, or None if no text."""
    if not text:
        return None
    try:
        from moviepy import TextClip

        margin = int(width * 0.06)  # 6% horizontal padding
        font_size = min(width // 42, 40)
        return (
            TextClip(
                text=text,
                font_size=font_size,
                color="white",
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(width - 2 * margin, None),
            )
            .with_position(("center", height * 0.7))
            .with_duration(duration)
        )
    except ImportError:
        return None
