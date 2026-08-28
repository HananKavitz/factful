"""Video rendering settings model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoSettings(BaseModel):
    fps: int = Field(default=24, ge=1, le=60)
    width: int = Field(default=640, ge=320, le=7680)
    height: int = Field(default=360, ge=240, le=4320)
    min_slide_seconds: float = Field(default=5.0, ge=1.0)
    voice: str = Field(default="en-US-AriaNeural", min_length=1)
    image_relevance_mode: str = Field(default="keyword", pattern="^(keyword|noun_jaccard)$")
    unsplash_api_key: str = Field(
        default="",
        description="Unsplash API access key. Empty = ImageSourceError at pre-validation.",
    )
    max_concurrent_fetches: int = Field(
        default=3, ge=1, le=10,
        description="Max parallel image downloads + TTS generations.",
    )
