"""LLM-based image source: generates images via text-to-image API."""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path

import httpx

from factful.video.prompt_generator import PromptGenerator
from factful.video.quality_gate import QualityGate
from factful.video.sources import ImageSourceError

logger = logging.getLogger(__name__)

_OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images/generation"


class LLMImageSource:
    """Image source that generates images using an LLM text-to-image model.

    Implements the ImageSource protocol. Uses a PromptGenerator to create
    rich prompts from slide content, runs them through a QualityGate for
    validation, and then sends them to an image generation API.

    Args:
        api_key: OpenRouter (or compatible) API key.
        prompt_generator: Generates image prompts from slide content.
        quality_gate: Validates prompt quality before generation.
        image_model: The image generation model name
            (e.g. "openai/gpt-image-3", "stability-ai/sdxl").
        http_client: Optional pre-configured HTTP client (for testing).
        cache_dir: Directory for caching generated images.
        timeout: HTTP timeout for image generation requests.
        max_retries: Number of retry attempts on API errors.
        regenerate_on_failure: If True, retry prompt generation with a
            refinement request when quality validation fails.
    """

    def __init__(
        self,
        *,
        api_key: str,
        prompt_generator: PromptGenerator,
        quality_gate: QualityGate,
        image_model: str = "openai/gpt-image-3",
        http_client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        regenerate_on_failure: bool = True,
    ) -> None:
        if not api_key:
            raise ImageSourceError("LLM image API key not configured")

        self._api_key = api_key
        self._prompt_generator = prompt_generator
        self._quality_gate = quality_gate
        self._image_model = image_model
        self._client = http_client or httpx.Client(timeout=timeout)
        self._cache_dir = cache_dir or Path("factful_videos/images")
        self._timeout = timeout
        self._max_retries = max_retries
        self._regenerate_on_failure = regenerate_on_failure

    def validate(self, *, heading: str, body: str) -> str | None:
        """Pre-validate: ensure API key is configured.

        The prompt enrichment and quality check happen at fetch() time
        since they require an LLM call.
        """
        if not self._api_key:
            return "LLM image API key not configured"
        return None

    def fetch(
        self,
        *,
        heading: str,
        body: str,
        output_path: Path,
    ) -> Path:
        """Generate an image for the slide and write it to output_path.

        Flow:
            1. Generate rich prompt via PromptGenerator
            2. Validate via QualityGate (structure + SBERT semantic check)
            3. If validation fails and regenerate_on_failure: refine prompt
            4. Check cache
            5. Send to image generation API
            6. Decode and save image + cache

        Args:
            heading: The slide heading.
            body: The slide body text.
            output_path: Where to write the generated image file.

        Returns:
            output_path on success.

        Raises:
            ImageSourceError: if prompt generation, validation, or
                image generation fails.
        """
        # Step 1+2: Generate and validate prompt
        prompt = self._generate_and_validate_prompt(heading, body)

        # Step 3: Check cache
        cache_path = self._cache_path(prompt)
        if cache_path.exists():
            _copy_cached(cache_path, output_path)
            return output_path

        # Step 4: Generate image
        image_data = self._generate_with_retries(prompt, heading)

        # Step 5: Save to output + cache
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_data)

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(image_data)

        return output_path

    def _generate_and_validate_prompt(self, heading: str, body: str) -> str:
        """Generate a prompt and validate it through the quality gate.

        If validation fails and regenerate_on_failure is True, attempts
        a second pass with a refinement prompt instructing the LLM to
        fix the identified issues.
        """
        try:
            prompt = self._prompt_generator.enrich(heading, body)
        except Exception as exc:
            raise ImageSourceError(
                f"failed to generate prompt for slide '{heading}': {exc}"
            ) from exc

        is_valid, issues, _ = self._quality_gate.validate_and_score(prompt, heading, body)
        if is_valid:
            return prompt

        if self._regenerate_on_failure:
            logger.info(
                "prompt quality failed for slide '%s', refining: %s",
                heading,
                ", ".join(issues),
            )
            try:
                refined = self._prompt_generator.refine(prompt, issues)
                is_valid2, _, _ = self._quality_gate.validate_and_score(refined, heading, body)
                if is_valid2:
                    return refined
            except Exception as exc:
                logger.warning("prompt refinement failed: %s", exc)

        raise ImageSourceError(f"prompt quality failed for slide '{heading}': {', '.join(issues)}")

    def _cache_path(self, prompt: str) -> Path:
        """Return the cache path for a given prompt."""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        return self._cache_dir / f"{prompt_hash}.png"

    def _generate_with_retries(self, prompt: str, heading: str) -> bytes:
        """Call the image generation API with retry logic."""
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                return self._generate_image(prompt)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 400 <= status < 500:
                    raise ImageSourceError(
                        f"image generation rejected (HTTP {status}): "
                        f"{exc.response.text[:300]} for slide '{heading}'"
                    ) from exc
                last_exc = exc
                logger.info(
                    "image generation failed (HTTP %d), retrying (%d/%d)",
                    status,
                    attempt + 1,
                    self._max_retries,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.info(
                    "image generation failed, retrying (%d/%d): %s",
                    attempt + 1,
                    self._max_retries,
                    exc,
                )

        raise ImageSourceError(
            f"image generation failed after {self._max_retries} attempts "
            f"for slide '{heading}': {last_exc}"
        ) from last_exc

    def _generate_image(self, prompt: str) -> bytes:
        """Send a single image generation request and return decoded bytes."""
        try:
            response = self._client.post(
                _OPENROUTER_IMAGES_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._image_model,
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x576",
                },
            )
        except httpx.HTTPError as exc:
            raise httpx.HTTPError(f"failed to reach image API: {exc}") from exc

        if response.status_code == 403:
            raise httpx.HTTPStatusError(
                "API key rejected", request=response.request, response=response
            )
        response.raise_for_status()

        data = response.json()

        b64_data = self._extract_image_data(data, response)
        if b64_data is None:
            raise ImageSourceError("image generation API returned no image data")

        try:
            return base64.b64decode(b64_data)
        except Exception as exc:
            raise ImageSourceError(f"failed to decode image data: {exc}") from exc

    @staticmethod
    def _extract_image_data(data: dict[str, object], response: httpx.Response) -> str | None:
        """Extract base64 image data from various API response formats."""
        # Format 1: {"data": [{"b64_json": "..."}]}
        response_data = data.get("data")
        if isinstance(response_data, list) and response_data:
            first = response_data[0]
            if isinstance(first, dict):
                if "b64_json" in first:
                    return str(first["b64_json"])

        # Format 2: {"data": [{"url": "data:image/png;base64,..."}]}
        if isinstance(response_data, list) and response_data:
            first = response_data[0]
            if isinstance(first, dict) and "url" in first:
                url = str(first["url"])
                if url.startswith("data:image/"):
                    return url.split(",", 1)[1] if "," in url else None

        # Format 3: {"image": "..."} (some models)
        if "image" in data:
            return str(data["image"])

        return None


def _copy_cached(src: Path, dst: Path) -> None:
    """Copy cached image to output path."""
    import shutil

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
