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
    topic: str
    score: float | None = None
    created_at: datetime
    updated_at: datetime


class StoryDetail(BaseModel):
    id: int
    title: str
    topic: str
    angle: str | None = None
    instructions: str | None = None
    markdown: str
    score: float | None = None
    created_at: datetime
    updated_at: datetime


class CreateStoryRequest(BaseModel):
    topic: str = Field(min_length=1)
    angle: str | None = None
    instructions: str | None = Field(default=None, max_length=4000)


class UpdateStoryRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    markdown: str | None = Field(default=None, min_length=1)


class EditStoryRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class UpdateStyleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    samples: str = Field(min_length=1, max_length=40000)


class SettingsOut(BaseModel):
    style: StyleProfile | None = None


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error", "cancelled"]
    stage: str | None = None
    error: str | None = None
    story_id: int | None = None
