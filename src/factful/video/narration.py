"""Per-scene narration synthesis and timing.

Generates one TTS clip per scene, measures each clip, and concatenates
them into a single voiceover track with offset-corrected subtitle
metadata.  Sizing each scene's visual to its measured narration is what
keeps the rendered video in sync with the voiceover.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from factful.video.composer import concat_audio_files, probe_duration
from factful.video.exceptions import TTSGenerationError
from factful.video.interfaces import Scene
from factful.video.subtitles import merge_tts_metadata
from factful.video.tts import generate_speech

logger = logging.getLogger(__name__)

# A speech function matches ``factful.video.tts.generate_speech``.
SpeechFn = Callable[..., Awaitable[tuple[Path, Path]]]


@dataclass
class NarrationTrack:
    """The combined voiceover and its per-scene timing.

    Attributes:
        audio_path: Concatenated voiceover WAV.
        metadata_path: Merged, offset-corrected WordBoundary JSONL.
        durations: Measured narration length (seconds) per scene, in order.
    """

    audio_path: Path
    metadata_path: Path
    durations: list[float]


async def synthesize_narration(
    scenes: Sequence[Scene],
    workdir: Path,
    *,
    voice: str,
    rate: str,
    pitch: str,
    tts: SpeechFn = generate_speech,
    probe: Callable[[Path], float] = probe_duration,
    concat: Callable[[list[Path], Path], Path] = concat_audio_files,
    merge: Callable[[list[tuple[Path, float]], Path], Path] = merge_tts_metadata,
    on_progress: Callable[[float], None] | None = None,
) -> NarrationTrack:
    """Synthesize, measure, and concatenate narration for every scene.

    Args:
        scenes: The script's scenes, in render order.
        workdir: Directory for per-scene WAVs and the combined track.
        voice: TTS voice name.
        rate: TTS speech rate.
        pitch: TTS pitch.
        tts: Speech generator (injectable for tests).
        probe: Duration probe (injectable for tests).
        concat: Audio concatenator (injectable for tests).
        merge: Subtitle metadata merger (injectable for tests).
        on_progress: Optional callback with the TTS completion fraction.

    Returns:
        A ``NarrationTrack`` with the voiceover and per-scene durations.

    Raises:
        TTSGenerationError: on empty input, empty narration, zero-length
            audio, or a TTS failure.
    """
    if not scenes:
        raise TTSGenerationError("cannot synthesize narration for an empty script")

    workdir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    scene_audio: list[Path] = []
    scene_meta: list[Path] = []
    durations: list[float] = []

    total = len(scenes)
    for idx, scene in enumerate(scenes):
        text = (scene.narration or "").strip()
        if not text:
            raise TTSGenerationError(f"scene {idx} has no narration text")

        scene_path = workdir / f"scene_{idx:04d}.wav"
        audio_path, metadata_path = await tts(
            text,
            scene_path,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )

        duration = probe(audio_path)
        if duration <= 0:
            raise TTSGenerationError(f"scene {idx} produced zero-length audio")

        scene_audio.append(audio_path)
        scene_meta.append(metadata_path)
        durations.append(duration)

        if on_progress is not None:
            on_progress((idx + 1) / total)

    voiceover_path = workdir / "voiceover.wav"
    concat(scene_audio, voiceover_path)

    segments: list[tuple[Path, float]] = []
    start = 0.0
    for metadata_path, duration in zip(scene_meta, durations, strict=True):
        segments.append((metadata_path, start))
        start += duration

    merged_path = workdir / "voiceover.jsonl"
    merge(segments, merged_path)

    logger.info(
        "Synthesized narration for %d scenes (total %.1fs)",
        total,
        sum(durations),
    )

    return NarrationTrack(
        audio_path=voiceover_path,
        metadata_path=merged_path,
        durations=durations,
    )
