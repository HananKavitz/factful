"""Generate rich image prompts from slide content using an LLM."""

from __future__ import annotations

from pydantic import BaseModel, Field

from factful.llm.client import ChatClient

# System prompt template that instructs the LLM to produce rich, specific
# image generation prompts from slide headings and body text.
_PROMPT_ENRICHMENT_TEMPLATE = """\
You are an expert image prompt engineer. Given a slide heading and its body
text from a fact-grounded article, generate a detailed, specific image prompt
that an AI image model (e.g. DALL-E 3, Stable Diffusion) can use to produce
a relevant, high-quality image.

Guidelines:
- Include concrete visual elements: objects, people, scenes, settings
- Specify photographic style: "photorealistic", "shot on Canon EOS R5", "4K"
- Include aesthetic details: lighting, color palette, composition
- Use aspect ratio notation: "--ar 16:9" for landscape slides
- Avoid abstract concepts without concrete visual representations
- Make the prompt 20-40 words long
- Return ONLY the prompt text, no explanations, no formatting

Heading: {heading}
Body: {body}

Image prompt:
"""

_REFINE_TEMPLATE = """\
The following image prompt failed quality validation.
Issues to fix:
{issues}

Original prompt: {original}

Rewrite to fix these issues. Maintain the core subject but add more concrete
visual details, style descriptors, and specific aesthetic guidance.
Make the prompt 20-40 words long. Return ONLY the improved prompt.
"""


class ImagePrompt(BaseModel):
    """Schema for the LLM-generated image prompt."""

    prompt: str = Field(min_length=1, description="A detailed image generation prompt")


class PromptGenerator:
    """Use an LLM to transform slide content into rich image prompts.

    Args:
        client: A ChatClient configured with the enrichment model
            (e.g. OpenRouterClient with gpt-4o-mini).
    """

    def __init__(self, *, client: ChatClient) -> None:
        self._client = client

    def enrich(self, heading: str, body: str) -> str:
        """Generate a rich image prompt from a slide heading and body.

        Args:
            heading: The slide heading text.
            body: The slide body text (context for image relevance).

        Returns:
            A detailed, image-model-ready prompt string.

        Raises:
            ValueError: If the LLM returns an unusable response.
        """
        body_for_prompt = body.strip() if body.strip() else "(no additional context)"
        prompt_text = _PROMPT_ENRICHMENT_TEMPLATE.format(heading=heading, body=body_for_prompt)

        result = self._client.chat_completion(
            prompt=prompt_text,
            schema=ImagePrompt,
            temperature=0.3,
        )

        if not isinstance(result, ImagePrompt):
            raise ValueError(f"expected ImagePrompt, got {type(result).__name__}")

        return result.prompt

    def refine(self, original_prompt: str, issues: list[str]) -> str:
        """Refine a prompt that failed quality validation.

        Args:
            original_prompt: The prompt that failed validation.
            issues: List of validation issues to fix.

        Returns:
            A refined, image-model-ready prompt string.

        Raises:
            ValueError: If the LLM returns an unusable response.
        """
        issues_text = "\n".join(f"  - {issue}" for issue in issues)
        prompt_text = _REFINE_TEMPLATE.format(issues=issues_text, original=original_prompt)

        result = self._client.chat_completion(
            prompt=prompt_text,
            schema=ImagePrompt,
            temperature=0.3,
        )

        if not isinstance(result, ImagePrompt):
            raise ValueError(f"expected ImagePrompt, got {type(result).__name__}")

        return result.prompt
