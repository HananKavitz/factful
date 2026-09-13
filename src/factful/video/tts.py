"""Text-to-speech using edge-tts.

Produces a WAV file and a WordBoundary JSONL metadata file used by
the subtitle builder.  Simplified from the old pipeline — no slide-level
chunking, just full-text-to-audio in one call.
"""

from __future__ import annotations

from pathlib import Path

from factful.video.exceptions import TTSGenerationError


async def generate_speech(
    text: str,
    output_path: Path,
    voice: str = "en-US-AriaNeural",
    rate: str = "-15%",
    pitch: str = "-5Hz",
) -> tuple[Path, Path]:
    """Generate a WAV audio file and a WordBoundary JSONL metadata file.

    Args:
        text: The full narration text to speak.
        output_path: Where to write the WAV file.
        voice: edge-tts voice name.
        rate: Speech rate (e.g. '-15%', 'slow').
        pitch: Speech pitch (e.g. '-5Hz', 'low').

    Returns:
        (wav_path, metadata_path).  The JSONL file has one JSON object
        per word with ``offset``, ``duration`` (in 100 ns ticks), and
        ``text`` fields.

    Raises:
        TTSGenerationError: if edge-tts fails or the output is empty.
    """
    if not text or not text.strip():
        raise TTSGenerationError("cannot generate speech from empty text")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import edge_tts
    except ImportError as exc:
        raise TTSGenerationError("edge-tts is not installed") from exc

    metadata_path = output_path.with_suffix(".jsonl")

    try:
        await edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            boundary="WordBoundary",
        ).save(
            str(output_path),
            metadata_fname=str(metadata_path),
        )
    except Exception as exc:
        raise TTSGenerationError(f"TTS generation failed for voice '{voice}': {exc}") from exc

    if not output_path.exists():  # noqa: ASYNC240
        raise TTSGenerationError(f"TTS output not created at {output_path}")

    return output_path, metadata_path
