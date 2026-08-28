"""Tests for the FFmpeg management module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from factful.video.exceptions import VideoRenderError
from factful.video.ffmpeg import ensure_ffmpeg, install_ffmpeg, check_ffmpeg_version


class TestEnsureFfmpeg:
    def test_returns_path_when_on_system_path(self) -> None:
        with patch("factful.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            result = ensure_ffmpeg()
        assert result == Path("/usr/bin/ffmpeg")

    def test_returns_bundled_when_not_on_path(self) -> None:
        with (
            patch("factful.video.ffmpeg.shutil.which", return_value=None),
            patch("factful.video.ffmpeg._bundled_ffmpeg_path") as mock_path,
        ):
            bundled = Path("/fake/bundled/ffmpeg")
            mock_path.return_value = bundled
            with patch.object(Path, "exists", return_value=True):
                result = ensure_ffmpeg()
        assert result == bundled

    def test_raises_when_not_found_anywhere(self) -> None:
        with (
            patch("factful.video.ffmpeg.shutil.which", return_value=None),
            patch("factful.video.ffmpeg._bundled_ffmpeg_path") as mock_path,
        ):
            mock_path.return_value = Path("/nonexistent/ffmpeg")
            with patch.object(Path, "exists", return_value=False):
                with pytest.raises(VideoRenderError, match="FFmpeg not found"):
                    ensure_ffmpeg()


class TestInstallFfmpeg:
    def test_returns_existing_path_if_already_installed(self) -> None:
        with patch("factful.video.ffmpeg._bundled_ffmpeg_path") as mock_path:
            bundled = Path("/fake/bundled/ffmpeg")
            mock_path.return_value = bundled
            with patch.object(Path, "exists", return_value=True):
                result = install_ffmpeg()
        assert result == bundled

    def test_raises_when_ffmpeg_downloader_not_installed(self) -> None:
        with (
            patch("factful.video.ffmpeg._bundled_ffmpeg_path") as mock_path,
            patch.object(Path, "exists", return_value=False),
            patch.dict(sys.modules, {"ffmpeg_downloader": None}),
        ):
            mock_path.return_value = Path("/fake/ffmpeg")
            with pytest.raises(VideoRenderError, match="not installed"):
                install_ffmpeg()

    def test_raises_when_download_fails(self) -> None:
        bundled = Path("/fake/bundled/ffmpeg")

        with (
            patch("factful.video.ffmpeg._bundled_ffmpeg_path", return_value=bundled),
            patch.object(Path, "exists", return_value=False),
            patch("factful.video.ffmpeg.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "network error"

            with pytest.raises(VideoRenderError, match="download failed"):
                install_ffmpeg()


class TestCheckFfmpegVersion:
    def test_returns_version_string(self) -> None:
        with (
            patch("factful.video.ffmpeg.ensure_ffmpeg", return_value=Path("/usr/bin/ffmpeg")),
            patch(
                "factful.video.ffmpeg.subprocess.run",
            ) as mock_run,
        ):
            mock_run.return_value.stdout = "ffmpeg version 6.0\n"
            mock_run.return_value.returncode = 0
            result = check_ffmpeg_version()
        assert result == "ffmpeg version 6.0"

    def test_returns_none_on_error(self) -> None:
        with patch(
            "factful.video.ffmpeg.ensure_ffmpeg",
            side_effect=VideoRenderError("not found"),
        ):
            assert check_ffmpeg_version() is None


def test_ensure_executable_noop_on_windows() -> None:
    from factful.video.ffmpeg import _ensure_executable

    if sys.platform == "win32":
        _ensure_executable(Path("dummy"))
    else:
        with patch.object(Path, "chmod") as mock_chmod:
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_mode = 0o644
                _ensure_executable(Path("/fake/ffmpeg"))
            mock_chmod.assert_called_once()