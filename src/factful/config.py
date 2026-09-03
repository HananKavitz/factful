from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Pipeline(BaseModel):
    max_passes: int = Field(default=3, ge=1)
    epsilon: float = Field(default=1.0, ge=0.0)
    delta: float = Field(default=0.5, ge=0.0)
    score_accept: int = Field(default=85, ge=0, le=100)
    revision_mode: str = Field(default="patch", pattern="^(patch|regenerate)$")


class Corroboration(BaseModel):
    min_sources: int = Field(default=2, ge=1)


class Gather(BaseModel):
    max_sources: int = Field(default=10, ge=1)
    search_days: int | None = Field(default=365, ge=1, le=365)


class Retrieval(BaseModel):
    top_k_passages: int = Field(default=3, ge=1)


class Verify(BaseModel):
    max_currency_years: float = Field(default=2.0, ge=0.0)


class Writer(BaseModel):
    profile: str = Field(default="kevich", min_length=1)
    min_words: int = Field(default=1500, ge=100)
    target_words: int = Field(default=2000, ge=100)
    max_words: int = Field(default=2500, ge=100)
    max_instructions_chars: int = Field(default=4000, ge=1)
    max_user_page_chars: int = Field(default=8000, ge=1)
    max_user_total_chars: int = Field(default=20000, ge=1)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _word_bounds_ordered(self) -> Writer:
        if not (self.min_words <= self.target_words <= self.max_words):
            raise ValueError("writer word bounds must satisfy min <= target <= max")
        return self


class LLM(BaseModel):
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    models: dict[str, str] = Field(default_factory=dict)


class Web(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_url: str = Field(default="sqlite:///./factful.db", min_length=1)
    auth_mode: str = Field(default="google", pattern="^(google|mock)$")
    session_secret: str = Field(default="dev-secret-change-me", min_length=1)
    google_client_id: str = ""
    google_client_secret: str = ""


from factful.video.settings import VideoSettings  # noqa: E402


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: Pipeline = Field(default_factory=Pipeline)
    corroboration: Corroboration = Field(default_factory=Corroboration)
    gather: Gather = Field(default_factory=Gather)
    retrieval: Retrieval = Field(default_factory=Retrieval)
    verify: Verify = Field(default_factory=Verify)
    writer: Writer = Field(default_factory=Writer)
    llm: LLM = Field(default_factory=LLM)
    web: Web = Field(default_factory=Web)
    video: VideoSettings = Field(default_factory=VideoSettings)


_WEB_ENV_VARS: dict[str, str] = {
    "database_url": "DATABASE_URL",
    "auth_mode": "AUTH_MODE",
    "session_secret": "SESSION_SECRET",
    "google_client_id": "GOOGLE_CLIENT_ID",
    "google_client_secret": "GOOGLE_CLIENT_SECRET",
}

_VIDEO_ENV_VARS: dict[str, str] = {
    "unsplash_api_key": "UNSPLASH_ACCESS_KEY",
    "image_api_key": "OPENROUTER_API_KEY",
}


def load_web_settings(
    settings: Settings | None = None, env: Mapping[str, str] | None = None
) -> Web:
    """Resolve web settings from YAML defaults with environment overrides."""
    base = settings.web if settings is not None else Web()
    overrides = {
        name: value
        for name, variable in _WEB_ENV_VARS.items()
        if (value := (env or {}).get(variable)) is not None
    }
    return Web.model_validate({**base.model_dump(), **overrides})


def load_video_settings(
    settings: Settings | None = None, env: Mapping[str, str] | None = None
) -> VideoSettings:
    """Resolve video settings from YAML defaults with environment overrides."""
    base = settings.video if settings is not None else VideoSettings()
    overrides = {
        name: value
        for name, variable in _VIDEO_ENV_VARS.items()
        if (value := (env or {}).get(variable)) is not None
    }
    return VideoSettings.model_validate({**base.model_dump(), **overrides})


def load_settings(path: Path | str | None = None) -> Settings:
    settings_path = Path(path) if path else Path("config/settings.yaml")
    data: dict[str, Any] = {}
    if settings_path.exists():
        data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(data)
