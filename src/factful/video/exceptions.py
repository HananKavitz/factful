"""Video generation exceptions.

Every error in the video pipeline inherits from VideoGenerationError.
The VideoService catches these and surfaces the message to the frontend
as the job error, and persists a failed Video record."""

from __future__ import annotations


class VideoGenerationError(Exception):
    """Base for all video generation errors. Message is frontend-safe."""


class ScriptError(VideoGenerationError):
    """Raised when the Script Director (LLM) fails to produce a valid script."""


class TTSGenerationError(VideoGenerationError):
    """Raised when edge-tts speech generation fails."""


class VideoSourceError(VideoGenerationError):
    """Raised when an external video source (Pexels, Kling) returns an error."""


class MusicSourceError(VideoSourceError):
    """Raised when a background music source (Openverse) returns an error."""


class CompositionError(VideoGenerationError):
    """Raised when video composition (moviepy/FFmpeg) fails."""


class NoUsableClipsError(VideoGenerationError):
    """Raised when no clips could be fetched from any configured source."""
