"""Tests for per-scene narration synthesis and timing."""

from __future__ import annotations

from pathlib import Path

import pytest

from factful.video.exceptions import TTSGenerationError
from factful.video.interfaces import Scene
from factful.video.narration import synthesize_narration


def _scene(text: str, duration: int = 5) -> Scene:
    return Scene(
        narration=text,
        visual_keywords=["x"],
        shot_type="wide",
        duration_seconds=duration,
    )


class TestSynthesizeNarration:
    async def test_calls_tts_once_per_scene(self, tmp_path: Path) -> None:
        """RED: one TTS call per scene (not a single full-text call)."""
        calls: list[str] = []

        async def fake_tts(text: str, path: Path, **kwargs: object) -> tuple[Path, Path]:
            calls.append(text)
            _touch(path)
            meta = path.with_suffix(".jsonl")
            _touch(meta)
            return path, meta

        scenes = [_scene("First."), _scene("Second."), _scene("Third.")]

        await synthesize_narration(
            scenes,
            tmp_path,
            voice="v",
            rate="-15%",
            pitch="-5Hz",
            tts=fake_tts,
            probe=lambda p: 5.0,
            concat=lambda paths, out: _touch(out),
            merge=lambda segments, out: _touch(out),
        )

        assert calls == ["First.", "Second.", "Third."]

    async def test_returns_measured_durations(self, tmp_path: Path) -> None:
        """RED: durations come from the measured audio, one per scene."""
        durations = iter([3.5, 7.25, 10.0])

        async def fake_tts(text: str, path: Path, **kwargs: object) -> tuple[Path, Path]:
            _touch(path)
            return path, path.with_suffix(".jsonl")

        track = await synthesize_narration(
            [_scene("a"), _scene("b"), _scene("c")],
            tmp_path,
            voice="v",
            rate="-15%",
            pitch="-5Hz",
            tts=fake_tts,
            probe=lambda p: next(durations),
            concat=lambda paths, out: _touch(out),
            merge=lambda segments, out: _touch(out),
        )

        assert track.durations == [3.5, 7.25, 10.0]

    async def test_concatenates_scene_audio(self, tmp_path: Path) -> None:
        """RED: the scene WAVs are concatenated into one voiceover."""
        concatenated: dict[str, list[Path]] = {}

        async def fake_tts(text: str, path: Path, **kwargs: object) -> tuple[Path, Path]:
            _touch(path)
            return path, path.with_suffix(".jsonl")

        def fake_concat(paths: list[Path], out: Path) -> Path:
            concatenated["paths"] = list(paths)
            return _touch(out)

        track = await synthesize_narration(
            [_scene("a"), _scene("b")],
            tmp_path,
            voice="v",
            rate="-15%",
            pitch="-5Hz",
            tts=fake_tts,
            probe=lambda p: 4.0,
            concat=fake_concat,
            merge=lambda segments, out: _touch(out),
        )

        assert len(concatenated["paths"]) == 2
        assert track.audio_path.exists()

    async def test_merges_metadata_with_cumulative_offsets(self, tmp_path: Path) -> None:
        """RED: subtitle segments are offset by the measured cumulative start."""
        captured: dict[str, list[tuple[Path, float]]] = {}
        durations = iter([4.0, 6.0])

        async def fake_tts(text: str, path: Path, **kwargs: object) -> tuple[Path, Path]:
            _touch(path)
            meta = path.with_suffix(".jsonl")
            _touch(meta)
            return path, meta

        def fake_merge(segments: list[tuple[Path, float]], out: Path) -> Path:
            captured["segments"] = list(segments)
            return _touch(out)

        await synthesize_narration(
            [_scene("a"), _scene("b")],
            tmp_path,
            voice="v",
            rate="-15%",
            pitch="-5Hz",
            tts=fake_tts,
            probe=lambda p: next(durations),
            concat=lambda paths, out: _touch(out),
            merge=fake_merge,
        )

        starts = [start for _, start in captured["segments"]]
        assert starts == [0.0, 4.0]

    async def test_empty_script_raises(self, tmp_path: Path) -> None:
        """RED: an empty scene list is a hard error."""
        with pytest.raises(TTSGenerationError, match="empty script"):
            await synthesize_narration(
                [],
                tmp_path,
                voice="v",
                rate="-15%",
                pitch="-5Hz",
            )

    async def test_empty_narration_raises(self, tmp_path: Path) -> None:
        """RED: a scene with no narration text is a hard error."""
        with pytest.raises(TTSGenerationError, match="no narration"):
            await synthesize_narration(
                [_scene("   ")],
                tmp_path,
                voice="v",
                rate="-15%",
                pitch="-5Hz",
            )

    async def test_zero_length_audio_raises(self, tmp_path: Path) -> None:
        """RED: a zero-length scene audio is a hard error."""

        async def fake_tts(text: str, path: Path, **kwargs: object) -> tuple[Path, Path]:
            _touch(path)
            return path, path.with_suffix(".jsonl")

        with pytest.raises(TTSGenerationError, match="zero-length"):
            await synthesize_narration(
                [_scene("a")],
                tmp_path,
                voice="v",
                rate="-15%",
                pitch="-5Hz",
                tts=fake_tts,
                probe=lambda p: 0.0,
                concat=lambda paths, out: _touch(out),
                merge=lambda segments, out: _touch(out),
            )


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path
