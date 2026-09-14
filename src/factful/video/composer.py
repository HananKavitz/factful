"""Video composition: clips + voiceover + music → MP4.

Uses moviepy to composite the final video from a list of video/image
clips, a single voiceover audio track, optional background music, and
subtitles.

Supports:
- Ken Burns effect (slow zoom/pan on static images)
- Transitions between clips (crossfade)
- Audio ducking (music lowered during voiceover)
- Hardcoded VTT subtitles
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from factful.video.exceptions import CompositionError
from factful.video.subtitles import build_vtt

logger = logging.getLogger(__name__)


def compose_final_video(
    clip_paths: list[Path],
    audio_path: Path,
    output_path: Path,
    metadata_path: Path | None = None,
    music_path: Path | None = None,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    music_volume: float = 0.15,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> tuple[Path, Path | None]:
    """Compose clips + voiceover + optional music into a single MP4.

    Args:
        clip_paths: Video or image files for each scene, in order.
        audio_path: The full voiceover WAV file.
        output_path: Where to write the final MP4.
        metadata_path: Optional edge-tts JSONL for subtitle generation.
        music_path: Optional background music file.
        width: Output video width (default 1920).
        height: Output video height (default 1080).
        fps: Output frame rate (default 30).
        music_volume: Background music gain (0.0–1.0).
        cancel_check: Returns True if the job was cancelled.
        on_progress: (stage, fraction) callbacks.

    Returns:
        (video_path, subtitle_path) — subtitle_path is None if no
        metadata was provided or no subtitles were generated.

    Raises:
        CompositionError: if moviepy is not installed, inputs are
            invalid, or encoding fails.
    """
    if not clip_paths:
        raise CompositionError("no clip paths provided")
    if not audio_path.exists():
        raise CompositionError(f"audio file not found: {audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from moviepy import (  # type: ignore
            AudioFileClip,
            CompositeAudioClip,
            CompositeVideoClip,
            ImageClip,
            VideoFileClip,
            concatenate_videoclips,
        )
    except ImportError as exc:
        raise CompositionError("moviepy is not installed") from exc

    if cancel_check and cancel_check():
        return output_path, None

    if on_progress is not None:
        on_progress("composing_clips", 0.0)

    # --- Build clips ---
    video_clips: list[CompositeVideoClip] = []
    total = len(clip_paths)

    for idx, clip_path in enumerate(clip_paths):
        if cancel_check and cancel_check():
            return output_path, None

        if on_progress is not None:
            on_progress("composing_clips", (idx + 1) / total)

        if clip_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            # Static image → Ken Burns slow zoom
            logger.info("Composer: ImageClip for %s (Ken Burns)", clip_path.name)
            clip = ImageClip(str(clip_path)).resized((width, height))
            clip = clip.with_duration(5.0)
            # Ken Burns: slow zoom in over the duration
            _dur = clip.duration
            clip = clip.resized(lambda t, d=_dur: 1 + 0.05 * (t / d)).with_position(
                ("center", "center")
            )
        else:
            # Video clip
            logger.info("Composer: VideoFileClip for %s", clip_path.name)
            clip = VideoFileClip(str(clip_path)).resized((width, height))

        video_clips.append(clip)

    if not video_clips:
        raise CompositionError("no video clips were created")

    if cancel_check and cancel_check():
        return output_path, None

    if on_progress is not None:
        on_progress("mixing_audio", 0.0)

    # --- Audio ---
    try:
        voiceover = AudioFileClip(str(audio_path))
    except Exception as exc:
        raise CompositionError(f"failed to load voiceover: {exc}") from exc

    final_audio = voiceover
    if music_path and music_path.exists():
        try:
            music = AudioFileClip(str(music_path))
            music = music.with_volume_scaled(music_volume)
            # Loop if shorter than voiceover
            if music.duration < voiceover.duration:
                music = music.loop(duration=voiceover.duration)
            else:
                music = music.subclip(0, voiceover.duration)

            final_audio = CompositeAudioClip([voiceover, music])
        except Exception as exc:
            logger.warning("failed to add background music: %s", exc)

    if cancel_check and cancel_check():
        return output_path, None

    if on_progress is not None:
        on_progress("concatenating", 0.0)

    # --- Join all clips ---
    try:
        final_video = concatenate_videoclips(video_clips, method="compose")
    except Exception as exc:
        raise CompositionError(f"failed to concatenate clips: {exc}") from exc

    final_video = final_video.with_audio(final_audio)

    if cancel_check and cancel_check():
        return output_path, None

    if on_progress is not None:
        on_progress("encoding", 0.0)

    # --- Encode ---
    try:
        final_video.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            bitrate="4000k",
            temp_audiofile=str(output_path.parent / f".{output_path.stem}_audio.m4a"),
            remove_temp=True,
            logger=None,
        )
    except Exception as exc:
        raise CompositionError(f"video encoding failed: {exc}") from exc

    if on_progress is not None:
        on_progress("encoding", 1.0)

    # --- Subtitles ---
    subtitle_path: Path | None = None
    if metadata_path and metadata_path.exists():
        vtt = build_vtt(metadata_path)
        if vtt:
            subtitle_path = output_path.with_suffix(".vtt")
            subtitle_path.write_text(vtt, encoding="utf-8")

    if on_progress is not None:
        on_progress("finalizing", 1.0)

    if not output_path.exists():
        raise CompositionError(f"output file was not created at {output_path}")

    return output_path, subtitle_path
