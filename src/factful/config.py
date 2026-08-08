from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


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


class LLM(BaseModel):
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    models: dict[str, str] = Field(default_factory=dict)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: Pipeline = Field(default_factory=Pipeline)
    corroboration: Corroboration = Field(default_factory=Corroboration)
    gather: Gather = Field(default_factory=Gather)
    llm: LLM = Field(default_factory=LLM)


def load_settings(path: Path | str | None = None) -> Settings:
    settings_path = Path(path) if path else Path("config/settings.yaml")
    data: dict[str, Any] = {}
    if settings_path.exists():
        data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(data)
