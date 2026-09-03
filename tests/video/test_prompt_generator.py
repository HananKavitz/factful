"""Tests for PromptGenerator."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from factful.video.prompt_generator import ImagePrompt, PromptGenerator


class _FakeChatClient:
    """Injectable fake ChatClient for PromptGenerator tests."""

    def __init__(
        self,
        *,
        respond: ImagePrompt | str | Exception = None,
        captured_prompt: dict | None = None,
    ) -> None:
        self._respond = respond
        self._captured = captured_prompt

    def chat_completion(
        self,
        *,
        prompt: str,
        schema: type,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> Any:
        if isinstance(self._respond, Exception):
            raise self._respond
        if isinstance(self._respond, str):
            return schema.model_validate(json.loads(self._respond))
        if self._captured is not None:
            self._captured["prompt"] = prompt
            self._captured["temperature"] = temperature
            self._captured["top_p"] = top_p
        return self._respond


class TestImagePromptSchema:
    def test_image_prompt_has_required_field(self) -> None:
        p = ImagePrompt(prompt="A detailed photo of a cat")
        assert p.prompt == "A detailed photo of a cat"

    def test_image_prompt_rejects_empty_string(self) -> None:
        with pytest.raises(ValidationError):
            ImagePrompt(prompt="")


class TestPromptGenerator:
    def test_enrich_returns_prompt_string(self) -> None:
        client = _FakeChatClient(respond=ImagePrompt(prompt="A detailed photo of a neuron"))
        gen = PromptGenerator(client=client)
        result = gen.enrich(
            "Neural Networks", "Deep learning models process information through layers"
        )
        assert isinstance(result, str)
        assert "neuron" in result.lower()

    def test_enrich_uses_low_creativity_temperature(self) -> None:
        captured: dict[str, Any] = {}
        client = _FakeChatClient(respond=ImagePrompt(prompt="x"), captured_prompt=captured)
        gen = PromptGenerator(client=client)
        gen.enrich("Test", "Some body text here")
        # Temperature should be deterministic-ish for prompt generation
        assert captured["temperature"] is not None

    def test_enrich_passes_heading_and_body_to_prompt(self) -> None:
        captured: dict[str, Any] = {}
        client = _FakeChatClient(respond=ImagePrompt(prompt="x"), captured_prompt=captured)
        gen = PromptGenerator(client=client)
        gen.enrich("Artificial Intelligence", "Machine learning transforms healthcare")
        prompt_text = captured["prompt"]
        assert "Artificial Intelligence" in prompt_text
        assert "Machine learning transforms healthcare" in prompt_text

    def test_enrich_raises_on_llm_error(self) -> None:
        client = _FakeChatClient(respond=ValueError("API error"))
        gen = PromptGenerator(client=client)
        with pytest.raises(ValueError, match="API error"):
            gen.enrich("Test", "Body")

    def test_enrich_handles_empty_body(self) -> None:
        captured: dict[str, Any] = {}
        client = _FakeChatClient(respond=ImagePrompt(prompt="x"), captured_prompt=captured)
        gen = PromptGenerator(client=client)
        gen.enrich("Just Heading", "")
        prompt_text = captured["prompt"]
        assert "Just Heading" in prompt_text

    def test_refine_returns_refined_prompt(self) -> None:
        client = _FakeChatClient(
            respond=ImagePrompt(prompt="A refined, detailed photo of a doctor")
        )
        gen = PromptGenerator(client=client)
        result = gen.refine(
            original_prompt="doctor photo",
            issues=["prompt too short: 2 words (minimum 15)", "no style/visual descriptor found"],
        )
        assert isinstance(result, str)
        assert "refined" in result

    def test_refine_passes_issues_and_original_to_prompt(self) -> None:
        captured: dict[str, Any] = {}
        client = _FakeChatClient(respond=ImagePrompt(prompt="x"), captured_prompt=captured)
        gen = PromptGenerator(client=client)
        gen.refine(original_prompt="vague prompt", issues=["too short", "no style"])
        prompt_text = captured["prompt"]
        assert "vague prompt" in prompt_text
        assert "too short" in prompt_text
        assert "no style" in prompt_text

    def test_refine_raises_on_llm_error(self) -> None:
        client = _FakeChatClient(respond=ValueError("refine failed"))
        gen = PromptGenerator(client=client)
        with pytest.raises(ValueError, match="refine failed"):
            gen.refine("original", ["issue"])
