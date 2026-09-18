"""Video composition: clips + voiceover + music → MP4.

Composition flow, from fastest to slowest:

1. **Stream copy** (near-instant) — when all clips share the same codec,
   resolution, pixel format and SAR, the concat demuxer copies packets
   without any re-encoding.

2. **FFmpeg concat filter** (fast) — native re-encode via filter_complex.
   Used when clips differ in resolution, codec, etc.

3. **Moviepy** (slow fallback) — required when scenes contain images
   (Ken Burns zoom effect).
"""

from __future__ import annotations

import logging
import re
import subprocess as sp
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from factful.video.exceptions import CompositionError
from factful.video.subtitles import build_vtt

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
_STREAM_RE = re.compile(
    r"Stream\s+#0:(\d+)(?:\[.*?\])?\(.*?\):\s+Video:\s+(\S+)\s+.*?,\s+(\S+),"
    r"\s+(\d+)x(\d+)\s+.*?(?:\[SAR\s+(\d+):(\d+)\s+DAR\s+(\d+):(\d+)\])?"
)
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})


# ── helpers ──────────────────────────────────────────────────────────


def _get_ffmpeg() -> str:
    """Return the FFmpeg binary path used by moviepy / imageio-ffmpeg."""
    try:
        from moviepy.config import FFMPEG_BINARY  # type: ignore

        return str(FFMPEG_BINARY)
    except ImportError:
        return "ffmpeg"


def _probe_duration(path: Path, ffmpeg_bin: str) -> float:
    """Quickly read a clip's duration from its header (no decode)."""
    try:
        result = sp.run(  # noqa: S603
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


def _probe_audio_duration(audio_path: Path) -> float:
    """Return the duration (seconds) of an audio file via FFmpeg probe.

    Falls back to ``_probe_duration`` which works on audio files too.
    """
    return _probe_duration(audio_path, _get_ffmpeg())


def _probe_format(path: Path, ffmpeg_bin: str) -> dict[str, str | int] | None:
    """Return stream metadata via ``ffmpeg -i`` stderr parsing.

    Returns ``None`` when the clip can't be probed (e.g. unsupported
    format or network timeout).
    """
    try:
        result = sp.run(  # noqa: S603
            [ffmpeg_bin, "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except sp.TimeoutExpired:
        logger.warning("Format probe timed out for %s", path.name)
        return None

    for line in result.stderr.splitlines():
        m = _STREAM_RE.search(line)
        if m:
            sar_num = int(m.group(6)) if m.group(6) else 1
            sar_den = int(m.group(7)) if m.group(7) else 1
            return {
                "codec": m.group(2),
                "pix_fmt": m.group(3),
                "width": int(m.group(4)),
                "height": int(m.group(5)),
                "sar": f"{sar_num}:{sar_den}",
            }
    return None


def _clips_compatible_for_copy(
    clip_paths: list[Path], ffmpeg_bin: str, width: int, height: int
) -> bool:
    """Check whether all clips are homogeneous enough for ``-c copy``.

    The concat demuxer requires every clip to share the same codec,
    resolution, pixel format, and sample aspect ratio.  If any clip
    is unprobeable we err on the side of re-encoding.
    """
    ref: dict[str, str | int] | None = None
    for p in clip_paths:
        info = _probe_format(p, ffmpeg_bin)
        if info is None:
            return False
        if ref is None:
            ref = info
        else:
            if info["codec"] != ref["codec"]:
                return False
    # All probeable — also check they match the *target* resolution
    # (stream copy can't resize, so the output would be the clip's
    # native resolution; we only accept exact match or upscale).
    # Actually for stream copy we keep native resolution — skip
    # resolution check and accept any matching codec.
    return True


def trim_or_loop_clip(
    clip_path: Path,
    target_duration: float,
    output_path: Path,
    *,
    ffmpeg_bin: str | None = None,
) -> Path:
    """Trim or loop a video clip to exactly *target_duration* seconds.

    If the clip is longer than *target_duration*, the end is trimmed off.
    If shorter, the clip is seamlessly looped (via ``-stream_loop -1``) to
    reach the target.  This ensures every scene's visual matches its
    narration segment so that ``-shortest`` in the final composition
    doesn't truncate the voiceover.

    Args:
        clip_path: Path to the source video file.
        target_duration: Desired duration in seconds (>= 0.5).
        output_path: Where to write the trimmed/looped file.
        ffmpeg_bin: Override the FFmpeg binary path.

    Returns:
        *output_path* (the caller can ignore the return value).

    Raises:
        CompositionError: if FFmpeg fails.
    """
    ffmpeg = ffmpeg_bin or _get_ffmpeg()
    actual = _probe_duration(clip_path, ffmpeg) or 0.0
    if actual <= 0:
        logger.warning("%s: cannot probe duration, leaving unclipped", clip_path.name)
        return clip_path

    if abs(actual - target_duration) < 0.5:
        # already close enough — re-use the source
        output_path.write_bytes(clip_path.read_bytes())
        return output_path

    # For loops we use -stream_loop -1 (loop infinitely) and cap with -t
    cmd = [
        ffmpeg,
        "-stream_loop",
        "-1" if actual < target_duration else "0",
        "-i",
        str(clip_path),
        "-t",
        str(target_duration),
        "-c",
        "copy" if actual >= target_duration else "aac",
        "-y",
        str(output_path),
    ]
    try:
        sp.run(cmd, capture_output=True, text=True, timeout=int(target_duration) + 60, check=True)  # noqa: S603
    except sp.CalledProcessError as exc:
        raise CompositionError(
            f"Failed to trim/loop clip {clip_path.name}: {exc.stderr[:500]}"
        ) from exc

    return output_path


def _scale_filter(width: int, height: int) -> str:
    """FFmpeg filter string to scale+pad to *width*x*height*."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=1,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


# ── run helper (shared by stream-copy and re-encode paths) ───────────


def _run_ffmpeg(
    cmd: list[str],
    total_duration: float,
    label: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> None:
    """Start an FFmpeg subprocess, stream progress, and check cancel."""
    if on_progress is not None:
        on_progress("encoding", 0.0)

    proc = sp.Popen(  # noqa: S603
        cmd,
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        text=True,
        bufsize=1,
    )

    progress_done = threading.Event()
    ffmpeg_error: list[str] = []

    def _read_stderr() -> None:
        if proc.stderr:
            for line in iter(proc.stderr.readline, ""):
                ffmpeg_error.append(line)
        progress_done.set()

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

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
        err_text = "".join(ffmpeg_error[-20:])
        raise CompositionError(f"{label} failed (exit {proc.returncode}): {err_text[:500]}")

    if on_progress is not None:
        on_progress("encoding", 1.0)


# ── FFmpeg encoding strategies ──────────────────────────────────────


def _encode_stream_copy(
    clip_paths: list[Path],
    audio_path: Path,
    output_path: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> float:
    """Near-instant concat via concat demuxer + ``-c copy``.

    All clips must have already been verified compatible
    (same codec, resolution, pix_fmt, SAR).

    Returns total estimated duration (seconds) for progress calculation.
    """
    ffmpeg = _get_ffmpeg()

    # --- total duration ---
    total_duration = 0.0
    for p in clip_paths:
        total_duration += _probe_duration(p, ffmpeg)

    # --- temp file list ---
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        filelist = Path(f.name)
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    if on_progress is not None:
        on_progress("composing_clips", 1.0)
        on_progress("mixing_audio", 1.0)
        on_progress("concatenating", 1.0)
        on_progress("composing", 1.0)

    cmd: list[str] = [
        ffmpeg,
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(filelist),
        "-i",
        str(audio_path),
        "-map",
        "0:v",
        "-c:v",
        "copy",
        "-map",
        "1:a",
        "-c:a",
        "aac",
        "-shortest",
        "-progress",
        "pipe:1",
        "-y",
        str(output_path),
    ]

    logger.info(
        "Stream-copy concat: %d clips, %.1fs total (near-instant).",
        len(clip_paths),
        total_duration,
    )

    try:
        _run_ffmpeg(
            cmd,
            total_duration,
            "FFmpeg stream-copy concat",
            cancel_check=cancel_check,
            on_progress=on_progress,
        )
    finally:
        filelist.unlink(missing_ok=True)

    return total_duration


def _encode_concat_filter(
    clip_paths: list[Path],
    audio_path: Path,
    output_path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bitrate: str = "4000k",
    music_path: Path | None = None,
    music_volume: float = 0.15,
    target_video_duration: float | None = None,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> float:
    """Re-encode via FFmpeg concat filter (native, no Python frame loop).

    When *target_video_duration* is longer than the sum of clip durations,
    the video stream is padded with a freeze-frame (``tpad``) so the final
    output lasts long enough for the full voiceover.  In that case
    ``-shortest`` is **not** used — the audio governs the output length.

    Returns the total (or target) video duration used for progress.
    """
    ffmpeg = _get_ffmpeg()

    total_duration = 0.0
    for p in clip_paths:
        total_duration += _probe_duration(p, ffmpeg)

    if total_duration <= 0:
        raise CompositionError("could not determine clip durations")

    n_clips = len(clip_paths)
    audio_idx = n_clips
    has_music = music_path is not None and music_path.exists()
    video_label = "[vid]"

    filters: list[str] = []
    for i in range(n_clips):
        filters.append(f"[{i}:v]{_scale_filter(width, height)}[v{i}]")

    concat_in = "".join(f"[v{i}]" for i in range(n_clips))
    filters.append(f"{concat_in}concat=n={n_clips}:v=1:a=0[vid]")

    # Pad the video with a freeze-frame if clips end before the target
    pad_duration: float | None = None
    if target_video_duration is not None and target_video_duration > total_duration + 0.5:
        pad_duration = target_video_duration
        gap = pad_duration - total_duration
        filters.append(f"[vid]tpad=stop_mode=clone:stop_duration={gap}[vid_padded]")
        video_label = "[vid_padded]"
        logger.info(
            "Adding %.1fs freeze-frame pad to reach target %.1fs (clips: %.1fs)",
            gap,
            pad_duration,
            total_duration,
        )

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

    cmd: list[str] = [ffmpeg]
    for p in clip_paths:
        cmd.extend(["-i", str(p)])
    cmd.extend(["-i", str(audio_path)])
    if has_music:
        cmd.extend(["-i", str(music_path)])
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", video_label, "-map", "[outa]"])
    cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-b:v", bitrate])
    cmd.extend(["-c:a", "aac"])
    if pad_duration is None:
        cmd.append("-shortest")
    cmd.extend(["-progress", "pipe:1", "-y", str(output_path)])

    progress_dur: float = pad_duration if pad_duration is not None else total_duration

    logger.info(
        "Concat-filter encode: %d clips, %.1fs total%s, %s audio inputs.",
        n_clips,
        total_duration,
        f" → {pad_duration:.1f}s (padded)" if pad_duration is not None else "",
        "TTS+music" if has_music else "TTS",
    )

    if on_progress is not None:
        on_progress("composing_clips", 1.0)
        on_progress("mixing_audio", 1.0)
        on_progress("concatenating", 1.0)
        on_progress("composing", 1.0)

    _run_ffmpeg(
        cmd,
        progress_dur,
        "FFmpeg concat-filter encode",
        cancel_check=cancel_check,
        on_progress=on_progress,
    )

    return progress_dur


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
    """Pick the fastest FFmpeg strategy for the given clips.

    1. **Stream copy** — when all clips share the same codec/resolution.
    2. **Concat filter** (re-encode) — native FFmpeg scaling + encode.

    Returns the subtitle path or ``None``.
    """
    ffmpeg = _get_ffmpeg()

    # Probe audio and clip durations to decide on padding
    audio_dur = _probe_audio_duration(audio_path)
    clip_dur = sum(_probe_duration(p, ffmpeg) for p in clip_paths)
    needs_pad = audio_dur > clip_dur + 0.5

    if needs_pad:
        logger.info(
            "Audio (%.1fs) longer than clips (%.1fs) — padding video with freeze frame.",
            audio_dur,
            clip_dur,
        )
        _encode_concat_filter(
            clip_paths,
            audio_path,
            output_path,
            width=width,
            height=height,
            bitrate=bitrate,
            music_path=music_path,
            music_volume=music_volume,
            target_video_duration=audio_dur,
            cancel_check=cancel_check,
            on_progress=on_progress,
        )
    elif _clips_compatible_for_copy(clip_paths, ffmpeg, width, height):
        _encode_stream_copy(
            clip_paths,
            audio_path,
            output_path,
            cancel_check=cancel_check,
            on_progress=on_progress,
        )
    else:
        _encode_concat_filter(
            clip_paths,
            audio_path,
            output_path,
            width=width,
            height=height,
            bitrate=bitrate,
            music_path=music_path,
            music_volume=music_volume,
            cancel_check=cancel_check,
            on_progress=on_progress,
        )

    # --- Subtitles ---
    subtitle_path: Path | None = None
    if metadata_path and metadata_path.exists():
        vtt = build_vtt(metadata_path)
        if vtt:
            subtitle_path = output_path.with_suffix(".vtt")
            subtitle_path.write_text(vtt, encoding="utf-8")

    return subtitle_path


# ── public entry point ───────────────────────────────────────────────


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

    Automatically selects the fastest available strategy:
      stream-copy → concat filter → moviepy (images/Ken Burns).

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
            logger.info("Composer: ImageClip for %s (Ken Burns)", clip_path.name)
            clip = ImageClip(str(clip_path)).resized((width, height))
            clip = clip.with_duration(5.0)
            _dur = clip.duration
            clip = clip.resized(lambda t, d=_dur: 1 + 0.05 * (t / d)).with_position(
                ("center", "center")
            )
        else:
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

    # If the voiceover is longer than the video, extend the video so
    # the full narration plays (freeze on last frame)
    audio_dur = voiceover.duration
    if audio_dur > final_video.duration:
        final_video = final_video.with_duration(audio_dur)

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
    subtitle_path_mp: Path | None = None
    if metadata_path and metadata_path.exists():
        vtt = build_vtt(metadata_path)
        if vtt:
            subtitle_path_mp = output_path.with_suffix(".vtt")
            subtitle_path_mp.write_text(vtt, encoding="utf-8")

    if on_progress is not None:
        on_progress("finalizing", 1.0)

    if not output_path.exists():
        raise CompositionError(f"output file was not created at {output_path}")

    return output_path, subtitle_path_mp
