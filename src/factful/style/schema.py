from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DeviceExample(BaseModel):
    label: str
    count: int = Field(default=0, ge=0)
    excerpt: str = ""


class StyleMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avg_sentence_words: float
    avg_paragraph_sentences: float
    paragraph_length_dist: list[int] = Field(default_factory=list)
    numeric_density: float = 0.0


class StyleExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str
    tone: str
    hook_patterns: list[str] = Field(default_factory=list)
    story_beats: list[str] = Field(default_factory=list)
    transitions: list[str] = Field(default_factory=list)
    rhetorical_devices: list[DeviceExample] = Field(default_factory=list)
    direct_address: list[DeviceExample] = Field(default_factory=list)
    characterization: list[DeviceExample] = Field(default_factory=list)
    opinion_hedges: list[str] = Field(default_factory=list)
    comparatives: list[str] = Field(default_factory=list)
    modals: list[str] = Field(default_factory=list)
    numeric_style: str = ""
    cta_style: str | None = None
    signoff_style: str | None = None


class StyleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    metrics: StyleMetrics
    extraction: StyleExtraction
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
