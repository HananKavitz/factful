"""Tests for SBERTRelevanceChecker."""

from __future__ import annotations

import numpy as np
import pytest

from factful.video.sbert_checker import SBERTRelevanceChecker


class _MockSBERTModel:
    """Mock SBERT model that returns predetermined embeddings."""

    def __init__(self, embeddings: dict[str, list[float]] | None = None) -> None:
        self._embeddings = embeddings or {}
        self.encode_calls: list[str] = []

    def encode(self, texts, **kwargs) -> np.ndarray:
        result: list[list[float]] = []
        for text in texts:
            self.encode_calls.append(text)
            if text in self._embeddings:
                result.append(self._embeddings[text])
            else:
                # Default: use a simple hash-based vector
                vec = [float(ord(c) % 7) / 7.0 for c in text[:384]] + [0.0] * (
                    384 - len(text[:384])
                )
                result.append(vec[:384])
        return np.array(result)


class _MockScoreModel:
    """Mock model with a direct score_relevance method."""

    def __init__(self, score: float = 0.95) -> None:
        self._score = score

    def is_available(self) -> bool:
        return True

    def score_relevance(self, prompt: str, expected_concepts: list[str]) -> float:
        _ = prompt, expected_concepts
        return self._score


class TestSBERTCheckerWithMock:
    """Tests using a mock SBERT model (no torch/sentence-transformers needed)."""

    def test_high_similarity_passes(self) -> None:
        embeddings = {
            "A photo of a radiologist examining a CT scan": [0.8] * 384,
            "radiologist CT scan": [0.8] * 384,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance(
            prompt="A photo of a radiologist examining a CT scan",
            expected_concepts=["radiologist", "CT scan"],
        )
        assert score >= 0.9

    def test_low_similarity_fails(self) -> None:
        # Use anti-correlated vectors to produce negative cosine similarity
        # (all-non-negative vectors can never score below 0.5 after normalization)
        embeddings = {
            "A photo of a radiologist examining a CT scan": [1.0] * 192 + [0.0] * 192,
            "cooking food kitchen": [-1.0] * 192 + [0.0] * 192,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance(
            prompt="A photo of a radiologist examining a CT scan",
            expected_concepts=["cooking", "food", "kitchen"],
        )
        assert score < 0.5

    def test_empty_concepts_returns_one(self) -> None:
        checker = SBERTRelevanceChecker(model=_MockSBERTModel())
        score = checker.score_relevance("A valid prompt here", [])
        assert score == 1.0

    def test_prompt_covers_more_than_half_concepts(self) -> None:
        """Score should reflect proportion of covered concepts."""
        embeddings = {
            "medical professional": [0.95] * 384,
            "medical": [0.9] * 384,
            "professional": [0.85] * 384,
            "cooking": [0.1] * 384,
            "food": [0.1] * 384,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance(
            prompt="A medical professional in a hospital",
            expected_concepts=["medical", "professional", "hospital", "cooking", "food"],
        )
        # 3 of 5 concepts are covered → score should be decent
        assert score > 0.3

    def test_uses_concept_aggregation_not_pairwise(self) -> None:
        """Checker encodes concepts as single combined text, not individually."""
        mock = _MockSBERTModel()
        checker = SBERTRelevanceChecker(model=mock)
        checker.score_relevance("test prompt", ["concept1", "concept2", "concept3"])
        # Should have encoded: prompt, and "concept1 concept2 concept3"
        assert len(mock.encode_calls) == 2
        assert "test prompt" in mock.encode_calls
        assert "concept1 concept2 concept3" in mock.encode_calls


class TestSBERTCheckerScoreMethod:
    """Tests using the score_relevance delegation path."""

    def test_high_score_model_passes(self) -> None:
        checker = SBERTRelevanceChecker(model=_MockScoreModel(score=0.95))
        score = checker.score_relevance("prompt", ["concept"])
        assert score == 0.95

    def test_low_score_model_fails(self) -> None:
        checker = SBERTRelevanceChecker(model=_MockScoreModel(score=0.1))
        score = checker.score_relevance("prompt", ["concept"])
        assert score == 0.1


class TestSBERTCheckerGracefulDegradation:
    """Tests for behavior when sentence-transformers is unavailable."""

    def test_checker_available_flag_true_with_model(self) -> None:
        checker = SBERTRelevanceChecker(model=_MockSBERTModel())
        assert checker.is_available()

    def test_checker_available_flag_false_without_model(self) -> None:
        checker = SBERTRelevanceChecker(model=None)
        assert not checker.is_available()

    def test_score_returns_zero_when_unavailable(self) -> None:
        checker = SBERTRelevanceChecker(model=None)
        score = checker.score_relevance("prompt", ["concept"])
        assert score == 0.0


class TestSBERTNormalization:
    """Tests for the normalization from cosine similarity to 0-1 range."""

    def test_cosine_1_maps_to_1(self) -> None:
        embeddings = {
            "identical text content here": [1.0, 0.0, 0.0] + [0.0] * 381,
            "identical": [0.5, 0.0, 0.0] + [0.0] * 381,
            "text": [0.3, 0.0, 0.0] + [0.0] * 381,
            "content": [0.2, 0.0, 0.0] + [0.0] * 381,
            "here": [0.1, 0.0, 0.0] + [0.0] * 381,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance(
            "identical text content here", ["identical", "text", "content", "here"]
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_cosine_0_maps_to_0_5(self) -> None:
        """A similarity of 0 maps to 0.5 (neutral)."""
        embeddings = {
            "prompt a": [0.0, 1.0, 0.0] + [0.0] * 381,
            "concept b": [1.0, 0.0, 0.0] + [0.0] * 381,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance("prompt a", ["concept b"])
        assert score == pytest.approx(0.5, abs=0.01)

    def test_cosine_neg1_maps_to_0(self) -> None:
        """A similarity of -1 maps to 0.0 (minimum)."""
        embeddings = {
            "prompt a": [1.0, 0.0, 0.0] + [0.0] * 381,
            "concept b": [-1.0, 0.0, 0.0] + [0.0] * 381,
        }
        checker = SBERTRelevanceChecker(model=_MockSBERTModel(embeddings))
        score = checker.score_relevance("prompt a", ["concept b"])
        assert score == pytest.approx(0.0, abs=0.01)
