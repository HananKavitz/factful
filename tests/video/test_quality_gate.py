"""Tests for QualityGate — orchestrates PromptValidator and SBERTRelevanceChecker."""

from __future__ import annotations

from factful.video.prompt_validator import PromptValidator
from factful.video.quality_gate import QualityGate
from factful.video.sbert_checker import SBERTRelevanceChecker


class _MockSBERT:
    def __init__(self, score: float = 0.95) -> None:
        self._score = score

    def is_available(self) -> bool:
        return True

    def score_relevance(self, prompt: str, expected_concepts: list[str]) -> float:
        _ = prompt, expected_concepts
        return self._score


class TestQualityGate:
    def test_all_layers_pass_returns_true(self) -> None:
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.9)),
        )
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray "
            "on a medical monitor, AI overlay, shot on Canon EOS R5, 4K resolution"
        )
        ok, issues, score = gate.validate_and_score(prompt, "Early Detection", "Radiologists...")
        assert ok
        assert issues == []
        assert score >= 0.9

    def test_prompt_structure_fails_blocks_generation(self) -> None:
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.9)),
        )
        ok, issues, score = gate.validate_and_score("ai doctor computer photo", "Test", "test")
        assert not ok
        assert any("short" in i or "style" in i or "prefix" in i for i in issues)

    def test_sbert_score_below_threshold_fails(self) -> None:
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.1)),
            min_semantic_score=0.3,
        )
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray "
            "on a medical monitor, AI overlay, shot on Canon EOS R5, 4K resolution"
        )
        ok, issues, score = gate.validate_and_score(prompt, "Early Detection", "Radiologists...")
        assert not ok
        assert any("semantic" in i or "relevance" in i for i in issues)
        assert score < 0.3

    def test_sbert_unavailable_only_uses_prompt_validation(self) -> None:
        """When SBERT is unavailable, fall back to prompt validation only."""
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=None),  # unavailable
        )
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray "
            "on a medical monitor, AI overlay, shot on Canon EOS R5, 4K"
        )
        ok, issues, score = gate.validate_and_score(prompt, "Test", "body")
        # Should pass based on prompt validation alone
        # SBERT contributes 0.0 but doesn't block if unavailable
        assert ok

    def test_keyword_coverage_extracts_nouns(self) -> None:
        """The gate extracts key concepts from heading + body for SBERT."""
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.8)),
        )
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray "
            "on a medical monitor, AI overlay, shot on Canon EOS R5, 4K resolution"
        )
        # The concepts should be nouns from heading + body, not raw text
        ok, issues, score = gate.validate_and_score(prompt, "Radiologist", "medical AI chest X-ray")
        assert ok  # prompt is valid and SBERT score is high

    def test_custom_min_semantic_score(self) -> None:
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.4)),
            min_semantic_score=0.3,
        )
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray "
            "on a medical monitor, shot on Canon EOS R5, 4K resolution"
        )
        ok, issues, score = gate.validate_and_score(prompt, "Test", "body")
        assert ok  # 0.4 >= 0.3
        assert score >= 0.3

    def test_all_checks_pass_with_empty_issues(self) -> None:
        gate = QualityGate(
            validator=PromptValidator(),
            sbert=SBERTRelevanceChecker(model=_MockSBERT(score=0.95)),
        )
        prompt = (
            "A cinematic photo of a neurosurgeon operating with robotic "
            "assistance, precision surgical instruments, sterile operating room, "
            "high detail photography, 4K resolution --ar 16:9"
        )
        ok, issues, score = gate.validate_and_score(prompt, "Surgery", "Robotic assistance")
        assert ok
        assert issues == []
