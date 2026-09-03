"""Tests for PromptValidator."""

from __future__ import annotations

from factful.video.prompt_validator import PromptValidator


class TestPromptStructureValidation:
    """Tests for layer 1: prompt structure validation."""

    def test_valid_rich_prompt_passes(self) -> None:
        validator = PromptValidator()
        prompt = (
            "A photorealistic photo of a radiologist reviewing a chest X-ray on a "
            "medical monitor, with an AI overlay highlighting lung nodules, shot on "
            "Canon EOS R5, natural lighting, National Geographic style --ar 16:9"
        )
        ok, issues = validator.validate(prompt)
        assert ok
        assert issues == []

    def test_prompt_too_short_fails(self) -> None:
        validator = PromptValidator()
        ok, issues = validator.validate("AI doctor computer")
        assert not ok
        assert any("short" in i for i in issues)

    def test_prompt_without_style_descriptor_fails(self) -> None:
        validator = PromptValidator()
        prompt = (
            "A radiologist examining a chest X-ray on a medical monitor with "
            "AI overlay highlighting lung nodules and patient data visualization"
        )
        ok, issues = validator.validate(prompt)
        assert not ok
        assert any("style" in i or "descriptor" in i for i in issues)

    def test_prompt_with_weak_prefix_fails(self) -> None:
        validator = PromptValidator()
        prompt = (
            "topic: A photorealistic photo of a radiologist reviewing a chest "
            "X-ray on a medical monitor, AI overlay, shot on Canon EOS R5"
        )
        ok, issues = validator.validate(prompt)
        assert not ok
        assert any("prefix" in i for i in issues)

    def test_prompt_with_cinematic_style_passes(self) -> None:
        validator = PromptValidator()
        prompt = (
            "A cinematic scene of a futuristic laboratory with holographic "
            "data displays, glowing blue interfaces, scientists in white coats, "
            "dramatic lighting, 4K resolution, ultra realistic --ar 16:9"
        )
        ok, issues = validator.validate(prompt)
        assert ok
        assert issues == []

    def test_prompt_with_4k_descriptor_passes(self) -> None:
        validator = PromptValidator()
        prompt = (
            "Professional 4K photo of a neurosurgeon operating with robotic "
            "assistance, precision instruments, sterile operating room, "
            "medical technology, high detail photography"
        )
        ok, issues = validator.validate(prompt)
        assert ok
        assert issues == []

    def test_empty_prompt_fails(self) -> None:
        validator = PromptValidator(min_word_count=15)
        ok, issues = validator.validate("")
        assert not ok


class TestCustomThresholds:
    """Tests for configurable thresholds."""

    def test_custom_min_word_count(self) -> None:
        validator = PromptValidator(min_word_count=20)
        prompt = "A photorealistic photo of a doctor looking at a computer"
        # 11 words, threshold is 20
        ok, issues = validator.validate(prompt)
        assert not ok
        assert any("short" in i for i in issues)

    def test_custom_style_words(self) -> None:
        validator = PromptValidator(style_words=["realistic", "detailed", "photography"])
        prompt = (
            "A realistic and detailed photography of a radiologist examining "
            "a patient's medical scan on a high-resolution monitor, with AI "
            "annotations highlighting key areas of interest, professional "
            "medical setting, clinical environment"
        )
        ok, issues = validator.validate(prompt)
        assert ok
        assert issues == []
