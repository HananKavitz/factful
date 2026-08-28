"""FFmpeg binary management: PATH check, bundled fallback, and download."""

# mypy: disable-error-code="import-untyped"

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from factful.video.exceptions import VideoRenderError

_BUNDLED_DIR = Path("factful_videos/bin")


def ensure_ffmpeg() -> Path:
    """Return a path to a usable FFmpeg binary.

    Checks the system PATH first, then the bundled location
    (``factful_videos/bin/``). Does NOT auto-download.

    Returns:
        Path to the FFmpeg executable.

    Raises:
        VideoRenderError: if FFmpeg is not found on PATH or bundled.
    """
    # 1. System PATH
    system = shutil.which("ffmpeg")
    if system is not None:
        return Path(system)

    # 2. Bundled location
    bundled = _bundled_ffmpeg_path()
    if bundled.exists():
        _ensure_executable(bundled)
        return bundled

    raise VideoRenderError(
        "FFmpeg not found. Install it on your PATH or run `factful install-ffmpeg`."
    )


def install_ffmpeg() -> Path:
    """Download a portable FFmpeg binary to ``factful_videos/bin/``.

    Uses the ``ffmpeg-downloader`` package's CLI (``ffdl``) to handle
    platform detection and download. Idempotent: if already installed,
    returns the existing path.

    Returns:
        Path to the downloaded FFmpeg executable.

    Raises:
        VideoRenderError: if download fails or the platform is unsupported.
    """
    target = _bundled_ffmpeg_path()
    if target.exists():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        import ffmpeg_downloader as _  # noqa: F401  # needed for get_bin_dir below
    except ImportError as exc:
        raise VideoRenderError(
            "ffmpeg-downloader is not installed; run `uv sync` to install dependencies"
        ) from exc

    # ffmpeg-downloader installs to its own cache dir.
    # We run `ffdl install` (the CLI) and then copy the binary.
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "ffmpeg_downloader", "install", "--add-path"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise VideoRenderError(f"FFmpeg download failed: {result.stderr.strip()}")

        # Locate the installed binary — it's in ffmpeg\bin\ffmpeg.exe
        from ffmpeg_downloader._path import get_bin_dir

        bin_dir = Path(get_bin_dir())
        exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"

        # Check various possible locations
        candidates = [
            bin_dir / exe_name,
            bin_dir.parent / "ffmpeg" / "bin" / exe_name,
            bin_dir / "ffmpeg" / exe_name,
        ]
        installed_bin: Path | None = None
        for candidate in candidates:
            if candidate.exists():
                installed_bin = candidate
                break

        if installed_bin is None:
            raise VideoRenderError(
                "FFmpeg downloader ran but no binary was found. "
                f"Looked in: {', '.join(str(c) for c in candidates)}"
            )

        # Copy to our bundled location for reliable pathing
        import shutil

        shutil.copy2(installed_bin, target)
        _ensure_executable(target)
    except subprocess.TimeoutExpired:
        raise VideoRenderError("FFmpeg download timed out after 120 seconds") from None
    except Exception as exc:
        raise VideoRenderError(f"FFmpeg download failed: {exc}") from exc

    if not target.exists():
        raise VideoRenderError("FFmpeg downloader did not produce a usable binary")

    return target


def _bundled_ffmpeg_path() -> Path:
    """Return the expected bundled FFmpeg path for the current platform."""
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return _BUNDLED_DIR / name


def _ensure_executable(path: Path) -> None:
    """Ensure the binary has executable permission (no-op on Windows)."""
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | 0o111)


def check_ffmpeg_version() -> str | None:
    """Return FFmpeg version string, or None if unavailable."""
    try:
        result = subprocess.run(  # noqa: S603  # trusted path from ensure_ffmpeg()
            [str(ensure_ffmpeg()), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        return first_line.strip() if first_line else None
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired, VideoRenderError):
        return None
