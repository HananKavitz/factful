"""Tests for LLMImageSource."""

from __future__ import annotations

import base64 as _b64
from pathlib import Path

import httpx
import pytest

from factful.video.llm_image_source import LLMImageSource
from factful.video.sources import ImageSource, ImageSourceError

_DEFAULT_B64 = _b64.b64encode(b"placeholder-image-bytes").decode()


def _mock_image_response(b64_data: str = _DEFAULT_B64) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"url": f"data:image/png;base64,{b64_data}"}]},
    )


class _StubPromptGenerator:
    """Stub PromptGenerator that returns predetermined prompts."""

    def __init__(self, prompt: str = "A detailed AI-generated image prompt") -> None:
        self._prompt = prompt
        self.last_heading = ""
        self.last_body = ""

    def enrich(self, heading: str, body: str) -> str:
        self.last_heading = heading
        self.last_body = body
        return self._prompt


class _StubQualityGate:
    """Stub QualityGate that always passes."""

    def __init__(self, should_pass: bool = True, issues: list[str] | None = None) -> None:
        self._should_pass = should_pass
        self._issues = issues or []
        self.last_prompt = ""

    def validate_and_score(
        self, prompt: str, heading: str, body: str
    ) -> tuple[bool, list[str], float]:
        self.last_prompt = prompt
        return self._should_pass, self._issues, 0.95


class TestLLMImageSourceProtocol:
    def test_implements_image_source_protocol(self) -> None:
        source = LLMImageSource(
            api_key="test-key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=_StubQualityGate(),
            http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        )
        assert isinstance(source, ImageSource)


class TestLLMImageSourceFetch:
    def test_fetch_saves_image_to_output_path(self, tmp_path: Path) -> None:
        image_bytes = b"fake-png-bytes"
        b64 = _b64.b64encode(image_bytes).decode()
        transport = httpx.MockTransport(lambda req: _mock_image_response(b64_data=b64))
        client = httpx.Client(transport=transport)
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator("A test image prompt"),
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        out = tmp_path / "result.png"
        result = source.fetch(heading="Test", body="Some body text", output_path=out)
        assert result == out
        assert out.exists()
        assert out.read_bytes() == image_bytes

    def test_fetch_uses_prompt_from_generator(self, tmp_path: Path) -> None:
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = req.content.decode()
            return _mock_image_response()

        client = httpx.Client(transport=httpx.MockTransport(handler))
        gen = _StubPromptGenerator("Radiant sunset over mountains")
        source = LLMImageSource(
            api_key="key",
            prompt_generator=gen,
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        out = tmp_path / "result.png"
        source.fetch(heading="Sunset", body="Mountains at dusk", output_path=out)

        assert gen.last_heading == "Sunset"
        assert gen.last_body == "Mountains at dusk"
        body = captured["body"]
        assert "Radiant sunset over mountains" in body

    def test_fetch_validates_prompt_before_generation(self, tmp_path: Path) -> None:
        gate = _StubQualityGate(should_pass=False, issues=["too vague"])
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=gate,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda r: _mock_image_response())
            ),
            cache_dir=tmp_path / "cache",
        )

        with pytest.raises(ImageSourceError, match="prompt quality"):
            source.fetch(heading="X", body="", output_path=tmp_path / "x.png")

    def test_fetch_empty_api_key_raises(self) -> None:
        with pytest.raises(ImageSourceError, match="API key"):
            LLMImageSource(
                api_key="",
                prompt_generator=_StubPromptGenerator(),
                quality_gate=_StubQualityGate(),
            )

    def test_fetch_403_raises_image_source_error(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(403))
        client = httpx.Client(transport=transport)
        source = LLMImageSource(
            api_key="bad-key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        with pytest.raises(ImageSourceError, match="rejected"):
            source.fetch(heading="X", body="", output_path=tmp_path / "x.png")

    def test_fetch_500_raises_image_source_error(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(500))
        client = httpx.Client(transport=transport)
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        with pytest.raises(ImageSourceError, match="failed"):
            source.fetch(heading="X", body="", output_path=tmp_path / "x.png")

    def test_fetch_uses_cache(self, tmp_path: Path) -> None:
        image_bytes = b"cached-image-data"
        b64 = _b64.b64encode(image_bytes).decode()
        call_count = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _mock_image_response(b64_data=b64)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator("same prompt every time"),
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        out1 = tmp_path / "result1.png"
        out2 = tmp_path / "result2.png"
        source.fetch(heading="Test", body="Body", output_path=out1)
        source.fetch(heading="Test", body="Body", output_path=out2)

        # API should only be called once due to caching
        assert call_count == 1
        assert out1.read_bytes() == out2.read_bytes() == image_bytes

    def test_fetch_uses_configured_image_model(self, tmp_path: Path) -> None:
        import json

        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = req.content.decode()
            return _mock_image_response()

        client = httpx.Client(transport=httpx.MockTransport(handler))
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=_StubQualityGate(),
            http_client=client,
            image_model="custom/image-model",
            cache_dir=tmp_path / "cache",
        )

        source.fetch(heading="T", body="B", output_path=tmp_path / "x.png")

        body = json.loads(captured["body"])
        assert body["model"] == "custom/image-model"

    def test_fetch_sends_prompt_in_request_body(self, tmp_path: Path) -> None:
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = req.content.decode()
            return _mock_image_response()

        client = httpx.Client(transport=httpx.MockTransport(handler))
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator("A radiant sunset over mountains"),
            quality_gate=_StubQualityGate(),
            http_client=client,
            cache_dir=tmp_path / "cache",
        )

        source.fetch(heading="Sunset", body="Dusk mountains", output_path=tmp_path / "out.png")

        import json

        body = json.loads(captured["body"])
        assert "prompt" in body
        assert "A radiant sunset over mountains" in body["prompt"]

    def test_fetch_regenerates_prompt_on_failure(self, tmp_path: Path) -> None:
        """When quality gate fails and regenerate_on_failure=True, retry."""
        image_bytes = b"regenerated-image"
        b64 = _b64.b64encode(image_bytes).decode()

        class _RefiningGenerator:
            def __init__(self) -> None:
                self.refine_called = False
                self.refined_prompt: str | None = None

            def enrich(self, heading: str, body: str) -> str:
                return "vague prompt"

            def refine(self, original: str, issues: list[str]) -> str:
                self.refine_called = True
                self.refined_prompt = "A photorealistic photo of a detailed medical scene"
                return self.refined_prompt

        gen = _RefiningGenerator()
        gate_call_count = 0

        def validate_and_score(prompt: str, heading: str, body: str):
            nonlocal gate_call_count
            gate_call_count += 1
            if gate_call_count == 1 and prompt == "vague prompt":
                return False, ["too short"], 0.1
            return True, [], 0.9

        class _GateStub:
            last_prompt = ""

            def validate_and_score(self, prompt: str, heading: str, body: str):
                self.last_prompt = prompt
                return validate_and_score(prompt, heading, body)

        gate = _GateStub()
        transport = httpx.MockTransport(lambda req: _mock_image_response(b64_data=b64))
        client = httpx.Client(transport=transport)
        source = LLMImageSource(
            api_key="key",
            prompt_generator=gen,  # type: ignore[arg-type]
            quality_gate=gate,  # type: ignore[arg-type]
            http_client=client,
            cache_dir=tmp_path / "cache",
            regenerate_on_failure=True,
        )

        out = tmp_path / "regen.png"
        result = source.fetch(heading="Test", body="Body", output_path=out)
        assert result == out
        assert out.read_bytes() == image_bytes
        assert gen.refine_called

    def test_fetch_does_not_regenerate_when_disabled(self, tmp_path: Path) -> None:
        gen = _StubPromptGenerator("vague prompt")
        gate = _StubQualityGate(should_pass=False, issues=["too short"])

        source = LLMImageSource(
            api_key="key",
            prompt_generator=gen,
            quality_gate=gate,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda r: _mock_image_response())
            ),
            cache_dir=tmp_path / "cache",
            regenerate_on_failure=False,
        )

        with pytest.raises(ImageSourceError, match="prompt quality"):
            source.fetch(heading="X", body="", output_path=tmp_path / "x.png")


class TestLLMImageSourceValidate:
    def test_validate_with_valid_key_returns_none(self) -> None:
        source = LLMImageSource(
            api_key="key",
            prompt_generator=_StubPromptGenerator(),
            quality_gate=_StubQualityGate(),
        )
        assert source.validate(heading="Test", body="Test body") is None

    def test_validate_with_empty_key_raises(self) -> None:
        with pytest.raises(ImageSourceError, match="API key"):
            LLMImageSource(
                api_key="",
                prompt_generator=_StubPromptGenerator(),
                quality_gate=_StubQualityGate(),
            )
