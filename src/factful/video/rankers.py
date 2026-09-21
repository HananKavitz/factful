"""Clip rankers: pick the most relevant Pexels clip for each scene.

A ranker sits between the Pexels search and the download step.

* ``NoOpRanker`` keeps the raw Pexels relevance order (the default).
* ``LlmVisionRanker`` shows candidate thumbnails to a vision LLM and keeps
  only the candidates that actually depict the scene, so an irrelevant clip
  is never downloaded.

Rankers are pure orchestration over an injected ``ChatClient``: no network
access happens here, which keeps the video unit tests hermetic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from factful.llm.client import ChatClient
from factful.video.interfaces import Scene

logger = logging.getLogger(__name__)

_DEFAULT_MIN_SCORE = 0.4


@dataclass(frozen=True)
class PexelsCandidate:
    """A single Pexels video and its ranked download links.

    Attributes:
        video_id: Pexels video id (for logging/deduplication).
        thumbnail_url: Preview image URL shown to the vision ranker, or None.
        links: Download links for this video, best file first.
    """

    video_id: int | None
    thumbnail_url: str | None
    links: tuple[str, ...]

    @property
    def link(self) -> str:
        """The best download link for this video."""
        return self.links[0]


class CandidateScore(BaseModel):
    """The vision model's relevance score for one candidate image."""

    index: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)


class PexelsRerank(BaseModel):
    """Structured output of the vision reranker."""

    scores: list[CandidateScore] = Field(default_factory=list)
    best_index: int | None = None


class ClipRanker(Protocol):
    """Orders Pexels candidates for a scene, best first.

    Returning an empty list means no candidate is good enough for the
    scene, which lets the caller route to AI generation or a placeholder
    instead of downloading an irrelevant clip.
    """

    def rank(self, scene: Scene, candidates: list[PexelsCandidate]) -> list[PexelsCandidate]: ...


class NoOpRanker:
    """Keep Pexels' own relevance order (no reranking)."""

    def rank(self, scene: Scene, candidates: list[PexelsCandidate]) -> list[PexelsCandidate]:
        return list(candidates)


def build_rerank_prompt(scene: Scene, count: int) -> str:
    """Build the vision-rerank prompt for one scene and ``count`` candidates."""
    keywords = ", ".join(scene.visual_keywords) if scene.visual_keywords else "(none)"
    return (
        "You are choosing the single best stock video clip for one scene of a documentary.\n\n"
        f"Scene narration: {scene.narration}\n"
        f"Visual keywords: {keywords}\n"
        f"Shot type: {scene.shot_type}\n\n"
        f"You are shown {count} candidate thumbnails, numbered 0 to {count - 1} "
        "in the order shown.\n"
        "For EACH candidate, rate how well it depicts the scene on a scale "
        "from 0 (unrelated) to 1 (perfect match). Weigh the subject, the "
        "setting, and the action; ignore production quality.\n"
        "Score every candidate. Then set best_index to the single best "
        "candidate, or null if none reaches 0.4."
    )


class LlmVisionRanker:
    """Rerank Pexels candidates by showing their thumbnails to a vision LLM.

    Only candidates that carry a thumbnail can be validated, so candidates
    without a preview image are excluded whenever ranking actually runs. If
    no candidate has a thumbnail, or the LLM call fails, the candidates are
    returned unchanged (falling back to Pexels' order) rather than failing
    the whole render.

    Args:
        client: A ``ChatClient`` (``OpenRouterClient``) for the rerank call.
        min_score: Minimum relevance score for a candidate to be kept.
    """

    def __init__(self, *, client: ChatClient, min_score: float = _DEFAULT_MIN_SCORE) -> None:
        self._client = client
        self._min_score = min_score

    def rank(self, scene: Scene, candidates: list[PexelsCandidate]) -> list[PexelsCandidate]:
        """Return candidates ordered by vision relevance, best first.

        Candidates scoring below ``min_score`` are dropped, and an empty
        result means nothing is good enough for the scene.
        """
        with_thumbnails = [c for c in candidates if c.thumbnail_url]
        if not with_thumbnails:
            return list(candidates)

        images = [c.thumbnail_url for c in with_thumbnails if c.thumbnail_url]
        try:
            result = self._client.chat_completion(
                prompt=build_rerank_prompt(scene, len(images)),
                schema=PexelsRerank,
                images=images,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("Pexels rerank failed, falling back to search order: %s", exc)
            return list(candidates)

        if not isinstance(result, PexelsRerank):
            logger.warning("Pexels rerank returned %s, falling back to search order", type(result))
            return list(candidates)

        if result.best_index is None:
            return []

        scores: dict[int, float] = {
            s.index: s.score for s in result.scores if 0 <= s.index < len(with_thumbnails)
        }
        order = sorted(range(len(with_thumbnails)), key=lambda i: scores.get(i, 0.0), reverse=True)
        return [with_thumbnails[i] for i in order if scores.get(i, 0.0) >= self._min_score]
