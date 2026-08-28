"""Tests for the edge-tts wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factful.video.exceptions import TTSError
from factful.video.tts import generate_speech


def _mock_edge_tts() -> MagicMock:
    """Create a mock edge_tts module that can be inserted into sys.modules."""
    mock = MagicMock()
    mock.Communicate = MagicMock()
    return mock


def test_generate_speech_writes_wav(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    mock_tts = _mock_edge_tts()

    with patch.dict(sys.modules, {"edge_tts": mock_tts}):
        instance = mock_tts.Communicate.return_value
        instance.save = AsyncMock()

        # Create the output file so the exists() check passes
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-wav-content")

        result = generate_speech("Hello world", out, voice="en-US-AriaNeural")

    assert result == out
    mock_tts.Communicate.assert_called_once_with(text="Hello world", voice="en-US-AriaNeural")
    instance.save.assert_awaited_once_with(str(out))


def test_generate_speech_uses_custom_voice(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    mock_tts = _mock_edge_tts()

    with patch.dict(sys.modules, {"edge_tts": mock_tts}):
        instance = mock_tts.Communicate.return_value
        instance.save = AsyncMock()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-wav")

        generate_speech("Hello", out, voice="en-US-GuyNeural")

    mock_tts.Communicate.assert_called_once_with(text="Hello", voice="en-US-GuyNeural")


def test_empty_text_raises(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    with pytest.raises(TTSError, match="empty text"):
        generate_speech("", out)


def test_whitespace_only_text_raises(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    with pytest.raises(TTSError, match="empty text"):
        generate_speech("   ", out)


def test_edge_tts_import_error_raises(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    with (
        patch.dict(sys.modules, {"edge_tts": None}),
        pytest.raises(TTSError, match="not installed"),
    ):
        generate_speech("Hello", out)


def test_edge_tts_failure_raises(tmp_path: Path) -> None:
    out = tmp_path / "test.wav"
    mock_tts = _mock_edge_tts()

    with patch.dict(sys.modules, {"edge_tts": mock_tts}):
        instance = mock_tts.Communicate.return_value
        instance.save = AsyncMock(side_effect=RuntimeError("API error"))
        with pytest.raises(TTSError, match="API error"):
            generate_speech("Hello", out)
