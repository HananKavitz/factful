"""Text-to-speech generation using edge-tts."""

from __future__ import annotations

import asyncio
from pathlib import Path

from factful.video.exceptions import TTSError


def generate_speech(text: str, output_path: Path, voice: str = "en-US-AriaNeural") -> Path:
    """Generate a WAV audio file from text using edge-tts.

    Args:
        text: The text to speak.
        output_path: Where to write the WAV file.
        voice: edge-tts voice name (default: en-US-AriaNeural).

    Returns:
        output_path on success.

    Raises:
        TTSError: if TTS generation fails.
    """
    if not text or not text.strip():
        raise TTSError("cannot generate speech from empty text")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import edge_tts
    except ImportError as exc:
        raise TTSError("edge-tts is not installed") from exc

    try:
        asyncio.run(edge_tts.Communicate(text=text, voice=voice).save(str(output_path)))
    except Exception as exc:
        raise TTSError(f"TTS generation failed for voice '{voice}': {exc}") from exc

    if not output_path.exists():
        raise TTSError(f"TTS output file was not created at {output_path}")

    return output_path
