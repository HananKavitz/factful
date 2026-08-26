from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    claim_id: str = Field(min_length=1)
    claim: str
    source_url: str
    source_title: str
    publisher: str
    publish_date: str
    key_stat: str
    quote_snippet: str
    passage_ref: str
    retrieved_at: datetime


class UserSourcePage(BaseModel):
    url: str
    title: str
    text: str


class SourceBundle(BaseModel):
    topic: str
    angle: str
    citations: list[Citation] = Field(default_factory=list)
    user_source_pages: list[UserSourcePage] = Field(default_factory=list)


class QueryExpansion(BaseModel):
    queries: list[str] = Field(min_length=4, max_length=6)


class MinedClaim(BaseModel):
    claim: str = Field(min_length=1)
    key_stat: str = Field(min_length=1)
    quote_snippet: str = Field(min_length=1)


class ClaimMineOutput(BaseModel):
    claims: list[MinedClaim] = Field(default_factory=list)


class RelevanceSelection(BaseModel):
    keep_claim_ids: list[str] = Field(default_factory=list)


class AttributionVerdict(BaseModel):
    status: Literal["supported", "unsupported"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class Draft(BaseModel):
    title: str = Field(min_length=1)
    markdown: str = Field(min_length=1)


class FactVerdict(BaseModel):
    claim_id: str
    status: Literal["verified", "unverified", "contradicted", "unsupported"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    corroborations: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    suggested_revision: str | None = None


class Issue(BaseModel):
    type: str
    severity: str
    message: str
    revision: str | None = None


class CritiqueReport(BaseModel):
    score: int = Field(ge=0, le=100)
    issues: list[Issue] = Field(default_factory=list)
    verdict: Literal["pass", "rework"]
