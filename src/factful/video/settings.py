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
        default=3,
        ge=1,
        le=10,
        description="Max parallel image downloads + TTS generations.",
    )

    # --- All-AI image generation settings ---
    image_source_type: str = Field(
        default="unsplash",
        pattern="^(unsplash|llm|hybrid)$",
        description="Which image source to use for slide backgrounds.",
    )
    prompt_model: str = Field(
        default="openai/gpt-4o-mini",
        description="LLM model for prompt enrichment (cheap, text-only).",
    )
    image_model: str = Field(
        default="openai/gpt-image-3",
        description="Image generation model for LLMImageSource.",
    )
    min_semantic_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum SBERT semantic similarity for prompt validation.",
    )
    enable_llm_verify: bool = Field(
        default=False,
        description="Use GPT-4o vision to verify image matches prompt (higher cost).",
    )
    regenerate_on_failure: bool = Field(
        default=True,
        description="Retry with refined prompt if quality check fails.",
    )
    debug_save_prompts: bool = Field(
        default=False,
        description="Save prompt text files alongside generated images for debugging.",
    )
