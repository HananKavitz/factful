"""Orchestrate multi-layer quality validation for image prompts.

Combines PromptValidator (structural checks) with SBERTRelevanceChecker
(semantic checks) to ensure generated prompts will produce relevant images.
"""

from __future__ import annotations

from factful.video.prompt_validator import PromptValidator
from factful.video.sbert_checker import SBERTRelevanceChecker, _extract_key_concepts


class QualityGate:
    """Multi-layer quality gate for image prompt validation.

    Layers:
        1. Prompt structure validation (always — no external deps)
        2. SBERT semantic relevance (optional — requires sentence-transformers)

    When SBERT is unavailable, the gate falls back to structure validation only.

    Args:
        validator: The PromptValidator for structural checks.
        sbert: The SBERTRelevanceChecker for semantic checks.
        min_semantic_score: Minimum normalized similarity (0.0–1.0)
            required to pass the SBERT layer.
    """

    def __init__(
        self,
        *,
        validator: PromptValidator,
        sbert: SBERTRelevanceChecker,
        min_semantic_score: float = 0.3,
    ) -> None:
        self._validator = validator
        self._sbert = sbert
        self._min_semantic_score = min_semantic_score

    def validate_and_score(
        self,
        prompt: str,
        heading: str,
        body: str,
    ) -> tuple[bool, list[str], float]:
        """Run all quality checks on a prompt.

        Args:
            prompt: The generated image prompt to validate.
            heading: The slide heading (used to extract expected concepts).
            body: The slide body text (used to extract expected concepts).

        Returns:
            A tuple of:
            - is_valid: True if all enabled checks pass
            - issues: List of failure descriptions (empty if valid)
            - semantic_score: The SBERT similarity score (0.0–1.0),
              or 0.0 if SBERT is unavailable
        """
        issues: list[str] = []

        # Layer 1: Structural validation (always runs)
        struct_ok, struct_issues = self._validator.validate(prompt)
        if not struct_ok:
            issues.extend(struct_issues)

        # Layer 2: SBERT semantic relevance (if available)
        expected_concepts = _extract_key_concepts(heading, body)
        semantic_score = 0.0

        if self._sbert is not None:
            semantic_score = self._sbert.score_relevance(prompt, expected_concepts)

            if self._sbert.is_available() and expected_concepts:
                # Only fail on low SBERT score if the model is actually available
                # and we have concepts to check against
                if semantic_score < self._min_semantic_score:
                    issues.append(
                        f"low semantic relevance: {semantic_score:.2f} "
                        f"(minimum {self._min_semantic_score})"
                    )
            elif expected_concepts:
                # SBERT unavailable but concepts exist — warn but don't block
                # The structural checks are sufficient in this case
                pass

        is_valid = len(issues) == 0
        return is_valid, issues, semantic_score
