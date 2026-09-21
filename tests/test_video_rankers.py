"""Tests for the Pexels clip rankers."""

from __future__ import annotations

from typing import Any

import pytest

from factful.video.interfaces import Scene
from factful.video.rankers import (
    CandidateScore,
    LlmVisionRanker,
    NoOpRanker,
    PexelsCandidate,
    PexelsRerank,
    build_rerank_prompt,
)


class FakeClient:
    """Stand-in ChatClient that records calls and returns a canned result."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _scene() -> Scene:
    return Scene(
        narration="Ocean waves crash against a rocky shore at sunset.",
        visual_keywords=["ocean", "sunset", "waves"],
        shot_type="wide",
    )


def _candidate(idx: int, *, thumb: str | None = None) -> PexelsCandidate:
    return PexelsCandidate(
        video_id=idx,
        thumbnail_url=thumb if thumb is not None else f"https://img/{idx}.jpg",
        links=(f"https://video/{idx}.mp4",),
    )


class TestNoOpRanker:
    def test_preserves_candidate_order(self) -> None:
        """RED: the no-op ranker leaves Pexels' order untouched."""
        candidates = [_candidate(0), _candidate(1), _candidate(2)]
        assert NoOpRanker().rank(_scene(), candidates) == candidates


class TestBuildRerankPrompt:
    def test_includes_scene_details_and_candidate_count(self) -> None:
        """RED: the prompt grounds the model in the scene and the count."""
        prompt = build_rerank_prompt(_scene(), 3)
        assert "Ocean waves crash" in prompt
        assert "ocean, sunset, waves" in prompt
        assert "wide" in prompt
        assert "3" in prompt


class TestLlmVisionRanker:
    def test_ranks_candidates_by_returned_score(self) -> None:
        """RED: candidates are reordered by the model's scores, best first."""
        client = FakeClient(
            PexelsRerank(
                scores=[
                    CandidateScore(index=0, score=0.2),
                    CandidateScore(index=1, score=0.9),
                    CandidateScore(index=2, score=0.6),
                ],
                best_index=1,
            )
        )
        ranker = LlmVisionRanker(client=client, min_score=0.4)

        ranked = ranker.rank(_scene(), [_candidate(0), _candidate(1), _candidate(2)])

        assert [c.video_id for c in ranked] == [1, 2]

    def test_filters_candidates_below_min_score(self) -> None:
        """RED: low-scoring candidates are dropped so they are never downloaded."""
        client = FakeClient(
            PexelsRerank(
                scores=[
                    CandidateScore(index=0, score=0.1),
                    CandidateScore(index=1, score=0.9),
                ],
                best_index=1,
            )
        )
        ranker = LlmVisionRanker(client=client, min_score=0.5)

        ranked = ranker.rank(_scene(), [_candidate(0), _candidate(1)])

        assert [c.video_id for c in ranked] == [1]

    def test_returns_empty_when_model_rejects_all(self) -> None:
        """RED: best_index=None gates the scene — no clip is acceptable."""
        client = FakeClient(
            PexelsRerank(
                scores=[
                    CandidateScore(index=0, score=0.2),
                    CandidateScore(index=1, score=0.3),
                ],
                best_index=None,
            )
        )
        ranker = LlmVisionRanker(client=client, min_score=0.4)

        assert ranker.rank(_scene(), [_candidate(0), _candidate(1)]) == []

    def test_sends_thumbnails_and_scene_to_client(self) -> None:
        """RED: the client receives the candidate thumbnails and scene prompt."""
        client = FakeClient(PexelsRerank(scores=[CandidateScore(index=0, score=0.9)], best_index=0))
        ranker = LlmVisionRanker(client=client, min_score=0.4)

        ranker.rank(_scene(), [_candidate(0, thumb="https://img/a.jpg")])

        call = client.calls[0]
        assert call["images"] == ["https://img/a.jpg"]
        assert call["temperature"] == 0.0
        assert call["schema"] is PexelsRerank
        assert "Ocean waves" in call["prompt"]

    def test_ignores_out_of_range_indices(self) -> None:
        """RED: hallucinated indices cannot select a real candidate."""
        client = FakeClient(
            PexelsRerank(
                scores=[
                    CandidateScore(index=0, score=0.5),
                    CandidateScore(index=99, score=1.0),
                ],
                best_index=99,
            )
        )
        ranker = LlmVisionRanker(client=client, min_score=0.4)

        ranked = ranker.rank(_scene(), [_candidate(0)])

        assert [c.video_id for c in ranked] == [0]

    def test_excludes_candidates_without_thumbnails(self) -> None:
        """RED: unverifiable candidates are dropped when ranking runs."""
        client = FakeClient(PexelsRerank(scores=[CandidateScore(index=0, score=0.9)], best_index=0))
        ranker = LlmVisionRanker(client=client, min_score=0.4)
        with_thumb = _candidate(0, thumb="https://img/a.jpg")
        without_thumb = PexelsCandidate(video_id=1, thumbnail_url=None, links=("https://v/1.mp4",))

        ranked = ranker.rank(_scene(), [with_thumb, without_thumb])

        assert ranked == [with_thumb]

    def test_returns_candidates_unchanged_when_none_have_thumbnails(self) -> None:
        """RED: without preview images there is nothing to rerank on."""
        client = FakeClient(PexelsRerank())
        ranker = LlmVisionRanker(client=client, min_score=0.4)
        candidates = [
            PexelsCandidate(video_id=0, thumbnail_url=None, links=("https://v/0.mp4",)),
            PexelsCandidate(video_id=1, thumbnail_url=None, links=("https://v/1.mp4",)),
        ]

        ranked = ranker.rank(_scene(), candidates)

        assert ranked == candidates
        assert client.calls == []

    def test_falls_back_to_unranked_on_llm_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """RED: an LLM outage degrades to Pexels order instead of failing."""
        caplog.set_level("WARNING", logger="factful.video.rankers")
        client = FakeClient(RuntimeError("boom"))
        ranker = LlmVisionRanker(client=client, min_score=0.4)
        candidates = [_candidate(0), _candidate(1)]

        ranked = ranker.rank(_scene(), candidates)

        assert ranked == candidates
        assert any("rerank" in r.message.lower() for r in caplog.records)
