"""Custom exceptions for the video rendering pipeline."""


class VideoRenderError(Exception):
    """Raised when video rendering cannot proceed (pre-validation or fatal error)."""


class ImageSourceError(VideoRenderError):
    """Raised when an ImageSource cannot produce an image for a slide."""


class TTSError(VideoRenderError):
    """Raised when text-to-speech generation fails."""


class CompositionError(VideoRenderError):
    """Raised when video composition (moviepy/ffmpeg) fails."""
