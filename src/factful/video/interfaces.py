"""Core interfaces for the pluggable video generation pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class VideoRequest:
    """Everything a VideoGenerator needs to produce a video.

    Attributes:
        markdown: The full article markdown.
        title: Article title (used for intro/outro).
        voice: TTS voice name (edge-tts format).
    """

    markdown: str
    title: str
    voice: str = "en-US-AriaNeural"


@dataclass
class VideoOutput:
    """Result of a successful video generation.

    Attributes:
        video_path: Path to the final MP4 file.
        subtitle_path: Path to the VTT subtitle file, or None.
        duration_seconds: Length of the video in seconds.
        resolution: e.g. "1920x1080".
        file_size_bytes: Size of the MP4 file.
    """

    video_path: Path
    subtitle_path: Path | None = None
    duration_seconds: float | None = None
    resolution: str | None = None
    file_size_bytes: int | None = None


@dataclass
class Scene:
    """A single scene in the script — one shot, one narration segment.

    Attributes:
        narration: Voiceover text for this scene (from the article).
        visual_keywords: Search terms for Pexels or prompt for Kling.
        shot_type: Visual style hint ("establishing", "close_up", "wide", "abstract").
        duration_seconds: How long this scene runs in the final video.
        need_ai_generation: True → Kling; False → Pexels stock clip.
        ai_confidence: 0.0–1.0 confidence that AI gen is truly needed.
    """

    narration: str
    visual_keywords: list[str] = field(default_factory=list)
    shot_type: str = "wide"
    duration_seconds: int = 8
    need_ai_generation: bool = False
    ai_confidence: float = 0.0


@dataclass
class VideoScript:
    """Structured breakdown of an article into a video script.

    Produced by the Script Director (LLM). Each Scene maps to one
    video clip in the final composition.  The overall music mood and
    pace guide non-scene choices (music track, transition speed).
    """

    scenes: list[Scene] = field(default_factory=list)
    music_mood: str = "neutral"
    overall_pace: str = "moderate"


@runtime_checkable
class VideoGenerator(Protocol):
    """A pluggable video generation strategy.

    Implementations are registered in VideoService by name and selected
    via the ``strategy`` parameter or ``default_strategy`` in settings.
    """

    def name(self) -> str:
        """Human-readable strategy name, e.g. 'stock', 'ai', 'hybrid'."""
        ...

    async def generate(
        self,
        request: VideoRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        script: VideoScript | None = None,
    ) -> VideoOutput:
        """Generate a video from the request.

        Args:
            request: All inputs for the generation.
            output_path: Where to write the final MP4.
            cancel_check: Returns True if the job was cancelled.
            on_progress: (stage_name, fraction_0_to_1).
            script: Optional pre-computed script. If None, the generator
                may run the Script Director itself.

        Returns:
            VideoOutput with paths and metadata.

        Raises:
            VideoGenerationError subclasses on failure.
        """
        ...


class VideoGeneratorFactory(Protocol):
    """Creates a VideoGenerator from settings and environment."""

    def __call__(
        self,
        settings: object,
        env: dict[str, str],
    ) -> VideoGenerator: ...
