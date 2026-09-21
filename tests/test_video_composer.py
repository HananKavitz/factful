"""Tests for the FFmpeg composition helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from factful.video import composer


class TestScaleFilter:
    def test_normalizes_frame_rate(self) -> None:
        """RED: the scale filter must normalize fps so concat + tpad is reliable."""
        filt = composer._scale_filter(1920, 1080, 30)
        assert "fps=30" in filt

    def test_scales_and_pads(self) -> None:
        """RED: the filter scales, pads, and sets SAR."""
        filt = composer._scale_filter(1280, 720, 25)
        assert "scale=1280:720" in filt
        assert "pad=1280:720" in filt
        assert "setsar=1" in filt
        assert "fps=25" in filt


class TestTrimOrLoopClip:
    def _capture(self, monkeypatch: object, actual: float) -> dict[str, list[str]]:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"mp4")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "probe_duration", lambda p, b=None: actual)  # type: ignore[attr-defined]
        monkeypatch.setattr(composer.sp, "run", fake_run)  # type: ignore[attr-defined]
        return captured

    def test_long_clip_is_trimmed_to_exact_target(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """RED: trimming re-encodes video-only to the exact narrated length."""
        captured = self._capture(monkeypatch, actual=10.0)
        src = tmp_path / "src.mp4"
        src.write_bytes(b"x")

        composer.trim_or_loop_clip(src, 4.0, tmp_path / "out.mp4")

        cmd = captured["cmd"]
        assert "-stream_loop" not in cmd
        assert "libx264" in cmd
        assert "-an" in cmd
        assert "4.0" in cmd

    def test_short_clip_is_looped_to_exact_target(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """RED: a clip shorter than the narration is looped."""
        captured = self._capture(monkeypatch, actual=1.0)
        src = tmp_path / "src.mp4"
        src.write_bytes(b"x")

        composer.trim_or_loop_clip(src, 6.0, tmp_path / "out.mp4")

        cmd = captured["cmd"]
        assert "-stream_loop" in cmd
        assert "-1" in cmd
        assert "libx264" in cmd


class TestProbeDuration:
    def test_parses_duration_from_ffmpeg_stderr(self, monkeypatch: object) -> None:
        """RED: the public probe parses the Duration line from FFmpeg."""
        completed = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            [], 0, stdout="", stderr="Duration: 00:00:12.50, start: 0.0"
        )
        monkeypatch.setattr(composer.sp, "run", lambda *a, **k: completed)  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]

        assert composer.probe_duration(Path("clip.mp4")) == 12.5


class TestConcatAudioFiles:
    def test_invokes_concat_demuxer(self, tmp_path: Path, monkeypatch: object) -> None:
        """RED: audio files are joined with the concat demuxer and PCM output."""
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"wav")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")  # type: ignore[attr-defined]

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer.sp, "run", fake_run)  # type: ignore[attr-defined]

        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        out = tmp_path / "voiceover.wav"

        result = composer.concat_audio_files([a, b], out)

        assert result == out
        assert "concat" in captured["cmd"]
        assert "pcm_s16le" in captured["cmd"]

    def test_empty_input_raises(self, tmp_path: Path) -> None:
        """RED: concatenating nothing is an error."""
        with pytest.raises(composer.CompositionError, match="no audio files"):
            composer.concat_audio_files([], tmp_path / "out.wav")


class TestMakePlaceholderClip:
    def test_uses_lavfi_color_source(self, tmp_path: Path, monkeypatch: object) -> None:
        """RED: placeholders are solid-color lavfi clips."""
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"mp4")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")  # type: ignore[attr-defined]

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer.sp, "run", fake_run)  # type: ignore[attr-defined]

        out = tmp_path / "placeholder.mp4"
        result = composer.make_placeholder_clip(6.0, out, width=640, height=360)

        assert result == out
        assert "lavfi" in captured["cmd"]
        assert any("color=c=black" in part for part in captured["cmd"])

    def test_non_positive_duration_raises(self, tmp_path: Path) -> None:
        """RED: a non-positive placeholder duration is an error."""
        with pytest.raises(composer.CompositionError, match="must be positive"):
            composer.make_placeholder_clip(0.0, tmp_path / "p.mp4")


class TestEncodeConcatFilter:
    def test_filter_complex_includes_target_fps(self, tmp_path: Path, monkeypatch: object) -> None:
        """RED: each input is normalized to the target fps before concat/tpad."""
        captured: dict[str, list[str]] = {}

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "probe_duration", lambda p, b=None: 5.0)  # type: ignore[attr-defined]

        def _fake_run(cmd: list[str], total_duration: float, label: str, **kwargs: object) -> None:
            captured["cmd"] = cmd

        monkeypatch.setattr(composer, "_run_ffmpeg", _fake_run)  # type: ignore[attr-defined]

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"x")
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"x")

        composer._encode_concat_filter(
            [clip],
            audio,
            tmp_path / "out.mp4",
            target_video_duration=10.0,
            fps=25,
        )

        cmd = captured["cmd"]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        assert "fps=25" in filter_complex

    def test_music_input_is_looped_and_mixed_without_normalizing(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """RED: a short track must loop, and amix must not attenuate the voiceover."""
        captured: dict[str, list[str]] = {}

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "probe_duration", lambda p, b=None: 5.0)  # type: ignore[attr-defined]

        def _fake_run(cmd: list[str], total_duration: float, label: str, **kwargs: object) -> None:
            captured["cmd"] = cmd

        monkeypatch.setattr(composer, "_run_ffmpeg", _fake_run)  # type: ignore[attr-defined]

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"x")
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"x")
        music = tmp_path / "music.mp3"
        music.write_bytes(b"x")

        composer._encode_concat_filter(
            [clip],
            audio,
            tmp_path / "out.mp4",
            music_path=music,
            music_volume=0.2,
        )

        cmd = captured["cmd"]
        music_idx = cmd.index(str(music))
        assert cmd[music_idx - 3 : music_idx] == ["-stream_loop", "-1", "-i"]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        assert "normalize=0" in filter_complex
        assert "volume=0.2" in filter_complex


class TestEncodeWithFFmpegMusic:
    def _patch(self, monkeypatch: object, audio_seconds: float) -> dict[str, object]:
        calls: dict[str, object] = {}

        monkeypatch.setattr(composer, "_get_ffmpeg", lambda: "ffmpeg")  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "_clips_compatible_for_copy", lambda *a, **k: True)  # type: ignore[attr-defined]

        def _probe(p: Path, b: str | None = None) -> float:
            return audio_seconds if p.name == "audio.wav" else 5.0

        monkeypatch.setattr(composer, "probe_duration", _probe)  # type: ignore[attr-defined]

        def _fake_stream(*a: object, **k: object) -> float:
            calls["stream"] = True
            return 5.0

        def _fake_concat(*a: object, **k: object) -> float:
            calls["concat"] = k
            return 5.0

        monkeypatch.setattr(composer, "_encode_stream_copy", _fake_stream)  # type: ignore[attr-defined]
        monkeypatch.setattr(composer, "_encode_concat_filter", _fake_concat)  # type: ignore[attr-defined]
        return calls

    def test_music_forces_concat_filter_over_stream_copy(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """RED: the stream-copy path drops music, so music must force the concat filter."""
        calls = self._patch(monkeypatch, audio_seconds=3.0)
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"x")
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"x")
        music = tmp_path / "music.mp3"
        music.write_bytes(b"x")

        composer._encode_with_ffmpeg([clip], audio, tmp_path / "out.mp4", music_path=music)

        assert "stream" not in calls
        assert calls["concat"]["music_path"] == music  # type: ignore[index]

    def test_no_music_still_uses_stream_copy(self, tmp_path: Path, monkeypatch: object) -> None:
        """RED: without music the fast stream-copy path is preserved."""
        calls = self._patch(monkeypatch, audio_seconds=3.0)
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"x")
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"x")

        composer._encode_with_ffmpeg([clip], audio, tmp_path / "out.mp4")

        assert calls.get("stream") is True
        assert "concat" not in calls
