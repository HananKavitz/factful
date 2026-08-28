from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from factful.style.schema import StyleProfile


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    picture: str | None = None


class MockLoginRequest(BaseModel):
    email: str = Field(min_length=1)
    name: str | None = None


class StorySummary(BaseModel):
    id: int
    title: str
    prompt: str
    score: float | None = None
    created_at: datetime
    updated_at: datetime


class StoryDetail(BaseModel):
    id: int
    title: str
    prompt: str
    angle: str | None = None
    instructions: str | None = None
    markdown: str
    score: float | None = None
    created_at: datetime
    updated_at: datetime
    videos: list[VideoInfo] = []


class CreateStoryRequest(BaseModel):
    prompt: str = Field(min_length=1)
    angle: str | None = None
    instructions: str | None = Field(default=None, max_length=4000)


class UpdateStoryRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    markdown: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)


class EditStoryRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class GenerateNoteRequest(BaseModel):
    title: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    instructions: str | None = Field(default=None, max_length=4000)


class GeneratedNote(BaseModel):
    note: str


class UpdateStyleRequest(BaseModel):
    samples: str = Field(min_length=1, max_length=40000)


class SettingsOut(BaseModel):
    style: StyleProfile | None = None
    temperature: float | None = None
    top_p: float | None = None


class UpdateGenerationSettingsRequest(BaseModel):
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error", "cancelled"]
    stage: str | None = None
    error: str | None = None
    story_id: int | None = None
    progress: int | None = None


class VideoInfo(BaseModel):
    id: int
    url: str
    voice: str
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    resolution: str | None = None
    status: str
    error_message: str | None = None
    file_exists: bool
    created_at: datetime


class RenderVideoRequest(BaseModel):
    voice: str | None = Field(default=None, min_length=1, max_length=128)
