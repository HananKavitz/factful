"""Video composition: clips + voiceover + music → MP4.

Uses FFmpeg concat filter directly for the common case (all video
clips), falling back to moviepy when images / Ken Burns are needed.
"""

from __future__ import annotations

import logging
import re
import subprocess as sp
import threading
from collections.abc import Callable
from pathlib import Path

from factful.video.exceptions import CompositionError
from factful.video.subtitles import build_vtt

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})


def _get_ffmpeg() -> str:
    """Return the FFmpeg binary path used by moviepy / imageio-ffmpeg."""
    try:
        from moviepy.config import FFMPEG_BINARY  # type: ignore[import-untyped]

        return str(FFMPEG_BINARY)
    except ImportError:
        # Fallback: hope it is on PATH
        return "ffmpeg"


def _probe_duration(path: Path, ffmpeg_bin: str) -> float:
    """Quickly read a clip's duration from its header (no decode)."""
    try:
        result = sp.run(  # noqa: S603  # ffmpeg_bin is from the trusted imageio-ffmpeg package
            [ffmpeg_bin, "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except sp.TimeoutExpired:
        logger.warning("Duration probe timed out for %s, assuming 8s", path.name)
        return 8.0

    for line in result.stderr.splitlines():
        m = _DURATION_RE.search(line)
        if m:
            h = int(m.group(1))
            m_ = int(m.group(2))
            s = float(m.group(3))
            return h * 3600 + m_ * 60 + s

    logger.warning("Could not parse duration for %s, assuming 8s", path.name)
    return 8.0


def _scale_filter(width: int, height: int) -> str:
    """FFmpeg filter string to scale+pad to *width*x*height*."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=1,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def _encode_with_ffmpeg(
    clip_paths: list[Path],
    audio_path: Path,
    output_path: Path,
    metadata_path: Path | None = None,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    bitrate: str = "4000k",
    music_path: Path | None = None,
    music_volume: float = 0.15,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> Path | None:
    """Encode video clips + audio via FFmpeg concat filter.

    This is *much* faster than moviepy's frame-by-frame Python pipe:
    FFmpeg decodes, scales, and re-encodes entirely in native code with
    zero frame iteration in Python.

    Returns the subtitle path or ``None``.
    """
    ffmpeg = _get_ffmpeg()

    # --- Estimate total duration (header-only probe) ---
    total_duration = 0.0
    for p in clip_paths:
        total_duration += _probe_duration(p, ffmpeg)

    if total_duration <= 0:
        raise CompositionError("could not determine clip durations")

    n_clips = len(clip_paths)
    audio_idx = n_clips  # TTS audio is the first non-video input
    has_music = music_path is not None and music_path.exists()

    # --- Build filter_complex ---
    filters: list[str] = []

    # 1) Scale each video input
    for i in range(n_clips):
        filters.append(f"[{i}:v]{_scale_filter(width, height)}[v{i}]")

    # 2) Concat video only (discard clip audio)
    concat_in = "".join(f"[v{i}]" for i in range(n_clips))
    filters.append(f"{concat_in}concat=n={n_clips}:v=1:a=0[vid]")

    # 3) Audio: format the TTS track (and mix with music if present)
    if has_music:
        filters.append(f"[{audio_idx}:a]adelay=0|0[a_tts]")
        filters.append(f"[{audio_idx + 1}:a]volume={music_volume}[a_music]")
        filters.append(
            "[a_tts][a_music]amix=inputs=2:duration=first,"
            "aformat=sample_rates=44100:channel_layouts=stereo[outa]"
        )
    else:
        filters.append(f"[{audio_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[outa]")

    filter_complex = ";".join(filters)

    # --- Build command ---
    cmd: list[str] = [ffmpeg]
    for p in clip_paths:
        cmd.extend(["-i", str(p)])
    cmd.extend(["-i", str(audio_path)])
    if has_music:
        cmd.extend(["-i", str(music_path)])
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "[vid]", "-map", "[outa]"])
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            bitrate,
        ]
    )
    cmd.extend(["-c:a", "aac", "-shortest"])
    cmd.extend(["-progress", "pipe:1", "-y", str(output_path)])

    logger.info(
        "FFmpeg encode: %d clips, %.1fs total, %s audio inputs.",
        n_clips,
        total_duration,
        "TTS+music" if has_music else "TTS",
    )

    # --- Run ---
    if on_progress is not None:
        on_progress("composing_clips", 1.0)
        on_progress("mixing_audio", 1.0)
        on_progress("concatenating", 1.0)
        on_progress("composing", 1.0)
        on_progress("encoding", 0.0)

    proc = sp.Popen(  # noqa: S603  # ffmpeg_bin is from the trusted imageio-ffmpeg package
        cmd,
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        text=True,
        bufsize=1,
    )

    # Parse -progress lines from stdout in a reader thread so we don't
    # block the stderr pipe (which can fill up on long encodes).
    progress_done = threading.Event()
    ffmpeg_error: list[str] = []

    def _read_stderr() -> None:
        if proc.stderr:
            for line in iter(proc.stderr.readline, ""):
                ffmpeg_error.append(line)
        progress_done.set()

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    # Read progress from stdout in the main thread
    try:
        for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
            if cancel_check and cancel_check():
                proc.kill()
                proc.wait()
                raise CompositionError("video encoding was cancelled")

            line_stripped = line.strip()
            if line_stripped.startswith("out_time_us="):
                try:
                    us = int(line_stripped.split("=")[1])
                    fraction = min(us / 1_000_000 / total_duration, 1.0)
                    if on_progress is not None:
                        on_progress("encoding", fraction)
                except (ValueError, ZeroDivisionError):
                    pass
    finally:
        proc.wait(timeout=30)
        progress_done.set()
        stderr_thread.join(timeout=5)

    if proc.returncode != 0:
        err_text = "".join(ffmpeg_error[-20:])  # last 20 lines
        raise CompositionError(f"FFmpeg encoding failed (exit {proc.returncode}): {err_text[:500]}")

    if on_progress is not None:
        on_progress("encoding", 1.0)

    # --- Subtitles ---
    subtitle_path: Path | None = None
    if metadata_path and metadata_path.exists():
        vtt = build_vtt(metadata_path)
        if vtt:
            subtitle_path = output_path.with_suffix(".vtt")
            subtitle_path.write_text(vtt, encoding="utf-8")

    return subtitle_path


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

    When every input is a video file (no images / Ken Burns) the
    composition is handed to FFmpeg's ``concat`` filter directly,
    which is **much** faster than moviepy's per-frame Python pipe.

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

    # Fast path — all video files → FFmpeg concat directly.
    if not any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in clip_paths):
        subtitle_path = _encode_with_ffmpeg(
            clip_paths=clip_paths,
            audio_path=audio_path,
            output_path=output_path,
            metadata_path=metadata_path,
            width=width,
            height=height,
            fps=fps,
            music_path=music_path,
            music_volume=music_volume,
            cancel_check=cancel_check,
            on_progress=on_progress,
        )

        if on_progress is not None:
            on_progress("finalizing", 1.0)

        if not output_path.exists():
            raise CompositionError(f"output file was not created at {output_path}")

        return output_path, subtitle_path

    # ------------------------------------------------------------------
    # Fallback — moviepy path (required for images / Ken Burns zoom)
    # ------------------------------------------------------------------
    try:
        import proglog
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

    class _EncodingProgressLogger(proglog.ProgressBarLogger):  # type: ignore[misc]
        """Reports moviepy frame-iteration progress to on_progress."""

        def __init__(
            self,
            on_progress: Callable[[str, float], None] | None,
            min_time_interval: float = 0.5,
        ) -> None:
            super().__init__(min_time_interval=min_time_interval)
            self._on_progress = on_progress

        def callback(self, **kw: object) -> None:
            bar = self.bars.get("frame_index")
            if bar is not None and self._on_progress is not None:
                total = bar.get("total")
                index = bar.get("index")
                if total and index is not None and total > 0:
                    self._on_progress("encoding", min(index / total, 1.0))

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

        if clip_path.suffix.lower() in (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
        ):
            # Static image → Ken Burns slow zoom
            logger.info("Composer: ImageClip for %s (Ken Burns)", clip_path.name)
            clip = ImageClip(str(clip_path)).resized((width, height))
            clip = clip.with_duration(5.0)
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

    final_audio: object = voiceover
    if music_path and music_path.exists():
        try:
            music = AudioFileClip(str(music_path))
            music = music.with_volume_scaled(music_volume)
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
            logger=_EncodingProgressLogger(on_progress) if on_progress is not None else None,
        )
    except Exception as exc:
        raise CompositionError(f"video encoding failed: {exc}") from exc

    if on_progress is not None:
        on_progress("encoding", 1.0)

    # --- Subtitles ---
    vtt_subtitle_path: Path | None = None
    if metadata_path and metadata_path.exists():
        vtt = build_vtt(metadata_path)
        if vtt:
            vtt_subtitle_path = output_path.with_suffix(".vtt")
            vtt_subtitle_path.write_text(vtt, encoding="utf-8")

    if on_progress is not None:
        on_progress("finalizing", 1.0)

    if not output_path.exists():
        raise CompositionError(f"output file was not created at {output_path}")

    return output_path, vtt_subtitle_path
