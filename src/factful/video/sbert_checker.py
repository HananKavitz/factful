"""SBERT-based semantic relevance checking for image prompts.

Uses sentence-transformers (all-MiniLM-L6-v2) to compute cosine similarity
between a generated image prompt and the key concepts extracted from the
slide content. Falls back gracefully when sentence-transformers/torch is
not available.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from factful.video.relevance import _tokenize

if TYPE_CHECKING:
    pass


def _extract_key_concepts(heading: str, body: str) -> list[str]:
    """Extract key concept nouns from slide heading and body text.

    Uses the existing tokenizers + noun extraction from relevance.py.
    Filters to content words (non-stopwords) that are likely nouns.
    """
    full_text = f"{heading} {body}"
    tokens = _tokenize(full_text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _cosine_similarity(a: Any, b: Any) -> float:
    """Compute cosine similarity between two vectors (list or ndarray).

    Uses pure Python to avoid numpy as a mypy-time dependency.
    """
    list_a = list(a)
    list_b = list(b)
    if len(list_a) != len(list_b):
        return 0.0
    dot = sum(x * y for x, y in zip(list_a, list_b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in list_a))
    norm_b = math.sqrt(sum(y * y for y in list_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _normalize_similarity(cosine: float) -> float:
    """Map cosine similarity (-1..1) to 0..1 range.

    -1 -> 0.0 (completely opposite)
     0 -> 0.5 (neutral)
    +1 -> 1.0 (identical)
    """
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


class _SBERTModel:
    """Wrapper around sentence-transformers SentenceTransformer.

    Imported lazily so the module loads even without torch installed.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any | None = None
        self._checked = False

    def _ensure_loaded(self) -> None:
        if self._checked:
            return
        self._checked = True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        except Exception:
            self._model = False  # Mark as unavailable

    def encode(self, texts: list[str]) -> Any:
        """Encode texts into embeddings. Raises if model unavailable."""
        self._ensure_loaded()
        if self._model is False or self._model is None:
            raise RuntimeError("sentence-transformers model not available")

        return self._model.encode(texts, show_progress_bar=False)

    def is_available(self) -> bool:
        """Check if the model can be loaded (lazy check)."""
        try:
            self._ensure_loaded()
            return self._model is not False and self._model is not None
        except Exception:
            return False


class SBERTRelevanceChecker:
    """Compute semantic similarity between image prompts and slide concepts.

    Uses SBERT embeddings to check whether a generated image prompt
    actually relates to the key concepts in the slide heading and body.
    Falls back gracefully when sentence-transformers is unavailable.

    Args:
        model_name: HuggingFace model name for sentence embeddings.
        model: Optional pre-instantiated SBERT-like model for testing
            (can provide encode(texts) or score_relevance(prompt, concepts)).
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        model: Any | None = None,
    ) -> None:
        if model is not None:
            self._model: Any = model  # Allow injection of mock model for tests
            self._model_name = ""
        else:
            self._model = _SBERTModel(model_name)
            self._model_name = model_name

    def is_available(self) -> bool:
        """Return True if the SBERT model is loaded and usable."""
        if self._model is None:
            return False
        return self._model.is_available() if hasattr(self._model, "is_available") else True

    def score_relevance(
        self,
        prompt: str,
        expected_concepts: list[str],
    ) -> float:
        """Score how well a prompt matches expected concepts (0.0–1.0).

        Encodes both the prompt and the joined expected concepts as text,
        then computes cosine similarity mapped to 0–1 range.

        Args:
            prompt: The generated image prompt text.
            expected_concepts: Key concept nouns from the slide content.

        Returns:
            A score from 0.0 (no match) to 1.0 (perfect match).
            Returns 1.0 if no concepts to check.
            Returns 0.0 if SBERT is unavailable but concepts exist.
        """
        if not expected_concepts:
            return 1.0  # Nothing to check — pass

        if self._model is None:
            return 0.0  # Unavailable but concepts exist — cannot verify

        if not self.is_available():
            return 0.0

        # Allow injected mock models to provide direct scoring
        # (skips encode + cosine similarity for testing convenience)
        if hasattr(self._model, "score_relevance") and callable(self._model.score_relevance):
            return float(self._model.score_relevance(prompt, expected_concepts))

        concepts_text = " ".join(expected_concepts)
        try:
            embeddings = self._model.encode([prompt, concepts_text])
            similarity = _cosine_similarity(embeddings[0], embeddings[1])
            return _normalize_similarity(similarity)
        except Exception:
            return 0.0  # Graceful degradation on any encoding error
