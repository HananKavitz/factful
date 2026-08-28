"""Tests for the video composer."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from factful.video.composer import compose_video
from factful.video.exceptions import CompositionError
from factful.video.settings import VideoSettings
from factful.video.slides import Slide


@pytest.fixture
def settings() -> VideoSettings:
    return VideoSettings(fps=30, width=640, height=360, min_slide_seconds=2.0)


@pytest.fixture
def slides() -> list[Slide]:
    return [
        Slide(heading="Intro", body_lines=["Welcome to the video."]),
        Slide(heading="Details", body_lines=["Here are the details."]),
    ]


@pytest.fixture
def image_paths(tmp_path: Path) -> list[Path]:
    paths = []
    for i in range(2):
        p = tmp_path / f"slide_{i}.jpg"
        p.write_bytes(b"fake-image")
        paths.append(p)
    return paths


@pytest.fixture
def audio_paths(tmp_path: Path) -> list[Path]:
    paths = []
    for i in range(2):
        p = tmp_path / f"slide_{i}.wav"
        p.write_bytes(b"fake-audio")
        paths.append(p)
    return paths


def _mock_moviepy() -> dict[str, MagicMock]:
    """Create mock moviepy module and return the key mocks."""
    mock_mod = MagicMock()
    mock_mod.ImageClip = MagicMock()
    mock_mod.AudioFileClip = MagicMock()
    mock_mod.AudioClip = MagicMock()
    mock_mod.TextClip = MagicMock()
    mock_mod.CompositeVideoClip = MagicMock()
    mock_mod.concatenate_videoclips = MagicMock()
    mock_mod.concatenate_audioclips = MagicMock()
    return mock_mod


def test_compose_video_creates_output(
    slides: list[Slide],
    image_paths: list[Path],
    audio_paths: list[Path],
    settings: VideoSettings,
    tmp_path: Path,
) -> None:
    out = tmp_path / "result.mp4"
    mock_mov = _mock_moviepy()

    with (
        patch("factful.video.composer.ensure_ffmpeg"),
        patch.dict(sys.modules, {"moviepy": mock_mov}),
    ):
        mock_img_instance = MagicMock()
        mock_mov.ImageClip.return_value = mock_img_instance
        mock_img_instance.resized.return_value = mock_img_instance

        mock_audio_instance = MagicMock()
        mock_audio_instance.duration = 3.0
        mock_audio_instance.fps = 44100
        mock_mov.AudioFileClip.return_value = mock_audio_instance
        mock_mov.AudioClip.return_value = mock_audio_instance

        mock_text_instance = MagicMock()
        mock_mov.TextClip.return_value = mock_text_instance

        mock_composite_instance = MagicMock()
        mock_mov.CompositeVideoClip.return_value = mock_composite_instance
        mock_composite_instance.with_duration.return_value = mock_composite_instance
        mock_composite_instance.with_audio.return_value = mock_composite_instance

        mock_concat_instance = MagicMock()
        mock_mov.concatenate_videoclips.return_value = mock_concat_instance

        mock_concat_audio_instance = MagicMock()
        mock_concat_audio_instance.duration = 7.0
        mock_mov.concatenate_audioclips.return_value = mock_concat_audio_instance

        # Write a fake output so the exists check passes
        out.write_bytes(b"fake-mp4")

        result = compose_video(
            slides=slides,
            image_paths=image_paths,
            audio_paths=audio_paths,
            output_path=out,
            settings=settings,
        )

    assert result == out
    assert mock_mov.concatenate_videoclips.called


def test_empty_slides_raises(
    settings: VideoSettings, tmp_path: Path
) -> None:
    with pytest.raises(CompositionError, match="empty slide list"):
        compose_video(
            slides=[],
            image_paths=[],
            audio_paths=[],
            output_path=tmp_path / "out.mp4",
            settings=settings,
        )


def test_mismatched_counts_raises(
    slides: list[Slide],
    image_paths: list[Path],
    audio_paths: list[Path],
    settings: VideoSettings,
    tmp_path: Path,
) -> None:
    with pytest.raises(CompositionError, match="does not match"):
        compose_video(
            slides=slides,
            image_paths=image_paths[:1],  # only 1 image
            audio_paths=audio_paths,
            output_path=tmp_path / "out.mp4",
            settings=settings,
        )


def test_audio_mismatch_raises(
    slides: list[Slide],
    image_paths: list[Path],
    audio_paths: list[Path],
    settings: VideoSettings,
    tmp_path: Path,
) -> None:
    with pytest.raises(CompositionError, match="does not match"):
        compose_video(
            slides=slides,
            image_paths=image_paths,
            audio_paths=audio_paths[:1],  # only 1 audio
            output_path=tmp_path / "out.mp4",
            settings=settings,
        )


def test_cancellation_during_compose_returns_early(
    slides: list[Slide],
    image_paths: list[Path],
    audio_paths: list[Path],
    settings: VideoSettings,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out.mp4"
    cancelled = False

    def cancel_check() -> bool:
        nonlocal cancelled
        return cancelled

    mock_mov = _mock_moviepy()

    with (
        patch("factful.video.composer.ensure_ffmpeg"),
        patch.dict(sys.modules, {"moviepy": mock_mov}),
    ):
        # cancelled before any composition work
        cancelled = True
        result = compose_video(
            slides=slides,
            image_paths=image_paths,
            audio_paths=audio_paths,
            output_path=out,
            settings=settings,
            cancel_check=cancel_check,
        )
    assert result == out
    # File should not have been created since we cancelled early
    assert not out.exists()


def test_slide_without_body_text_does_not_crash(
    settings: VideoSettings, tmp_path: Path
) -> None:
    slides_no_body = [Slide(heading="Only Heading", body_lines=[])]
    img = tmp_path / "img.jpg"
    img.write_bytes(b"fake")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    out = tmp_path / "out.mp4"
    mock_mov = _mock_moviepy()

    with (
        patch("factful.video.composer.ensure_ffmpeg"),
        patch.dict(sys.modules, {"moviepy": mock_mov}),
    ):
        mock_img = MagicMock()
        mock_mov.ImageClip.return_value = mock_img
        mock_img.resized.return_value = mock_img

        mock_aud = MagicMock()
        mock_aud.duration = 3.0
        mock_aud.fps = 44100
        mock_mov.AudioFileClip.return_value = mock_aud
        mock_mov.AudioClip.return_value = mock_aud

        mock_comp_instance = MagicMock()
        mock_mov.CompositeVideoClip.return_value = mock_comp_instance
        mock_comp_instance.with_duration.return_value = mock_comp_instance
        mock_comp_instance.with_audio.return_value = mock_comp_instance

        mock_concat_audio_instance = MagicMock()
        mock_concat_audio_instance.duration = 7.0
        mock_mov.concatenate_audioclips.return_value = mock_concat_audio_instance

        out.write_bytes(b"fake-mp4")

        result = compose_video(
            slides=slides_no_body,
            image_paths=[img],
            audio_paths=[audio],
            output_path=out,
            settings=settings,
        )
    assert result == out


def test_moviepy_import_error_raises(
    settings: VideoSettings, tmp_path: Path
) -> None:
    out = tmp_path / "out.mp4"
    with (
        patch("factful.video.composer.ensure_ffmpeg"),
        patch.dict(sys.modules, {"moviepy": None}),
        pytest.raises(CompositionError, match="not installed"),
    ):
        compose_video(
            slides=[Slide(heading="Test", body_lines=["body"])],
            image_paths=[tmp_path / "img.jpg"],
            audio_paths=[tmp_path / "audio.wav"],
            output_path=out,
            settings=settings,
        )