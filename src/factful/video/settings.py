"""Video generation settings model — configurable from settings.yaml."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoSettings(BaseModel):
    """Configuration for the video generation pipeline.

    Loaded from the ``video:`` section of ``config/settings.yaml``,
    with environment variable overrides for API keys.
    """

    # --- Strategy ---
    default_strategy: str = Field(
        default="hybrid",
        pattern="^(stock|ai|hybrid)$",
        description="Which generator to use when no strategy is requested.",
    )

    # --- Output ---
    width: int = Field(default=1920, ge=320, le=7680)
    height: int = Field(default=1080, ge=240, le=4320)
    fps: int = Field(default=30, ge=1, le=60)

    # --- TTS ---
    voice: str = Field(default="en-US-AriaNeural", min_length=1)
    tts_rate: str = Field(
        default="-15%",
        pattern=r"^[+-]\d+%$|^(x-slow|slow|medium|fast|x-fast)$",
    )
    tts_pitch: str = Field(
        default="-5Hz",
        pattern=r"^[+-]\d+Hz$|^(x-low|low|medium|high|x-high)$",
    )

    # --- Script Director ---
    script_director_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Cheap LLM for article → scene analysis (via OpenRouter).",
    )

    # --- AI video generation (Kling) ---
    ai_provider: str = Field(default="kling")
    ai_model: str = Field(default="kling/kling-1.6")
    ai_api_key_env: str = Field(default="KLING_API_KEY")
    ai_max_clips: int = Field(default=15, ge=1, le=50)
    ai_clip_duration_seconds: int = Field(default=5, ge=2, le=10)

    # --- Stock footage (Pexels) ---
    stock_provider: str = Field(default="pexels")
    stock_api_key_env: str = Field(default="PEXELS_API_KEY")
    stock_min_resolution: str = Field(default="1080p")

    # --- Pexels clip ranking ---
    clip_rank_mode: str = Field(
        default="none",
        pattern="^(none|llm_vision)$",
        description="How to rank Pexels results: keep search order or rerank with a vision LLM.",
    )
    clip_rank_model: str = Field(
        default="google/gemini-2.5-flash",
        description="Vision LLM used to rerank Pexels thumbnails (via OpenRouter).",
    )
    clip_rank_max_candidates: int = Field(default=6, ge=1, le=20)
    clip_rank_min_score: float = Field(default=0.4, ge=0.0, le=1.0)

    # --- Hybrid fine-tuning ---
    hybrid_ai_budget_seconds: int = Field(
        default=30,
        ge=0,
        description="Maximum seconds of AI-generated video per hybrid render.",
    )

    # --- Music ---
    music_enabled: bool = Field(default=True)
    music_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    music_license: str = Field(default="cc0", pattern="^cc0$")
    music_min_duration_seconds: int = Field(default=120, ge=1)
    music_max_duration_seconds: int = Field(default=300, ge=1)
    music_max_candidates: int = Field(default=20, ge=1, le=20)
