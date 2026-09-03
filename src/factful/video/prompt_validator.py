"""Validate generated image prompts for structural quality."""

from __future__ import annotations

# Style/visual descriptors that indicate a well-formed image prompt
DEFAULT_STYLE_WORDS: frozenset[str] = frozenset(
    {
        "photorealistic",
        "photo",
        "cinematic",
        "realistic",
        "ultra realistic",
        "4k",
        "8k",
        "hd",
        "high detail",
        "detailed",
        "professional photography",
        "professional photo",
        "shot on",
        "dslr",
        "canon",
        "nikon",
        "film",
        "photography",
        "illustration",
        "digital art",
        "oil painting",
        "watercolor",
    }
)

# Prefixes that indicate the LLM didn't enrich the prompt properly
_WEAK_PREFIXES: tuple[str, ...] = (
    "topic:",
    "subject:",
    "theme:",
    "query:",
    "search:",
    "keyword:",
    "prompt:",
    "description:",
)


class PromptValidator:
    """Validate that a generated image prompt has sufficient richness.

    Checks three structural properties:
    1. Minimum word count (default 15) — ensures enough detail.
    2. Style/visual descriptors present — ensures consistent aesthetic.
    3. No weak metadata prefixes — ensures the prompt is natural language.

    Args:
        min_word_count: Minimum number of words required.
        style_words: Set of style descriptors to look for (case-insensitive).
    """

    def __init__(
        self,
        min_word_count: int = 15,
        style_words: frozenset[str] | None = None,
    ) -> None:
        self._min_word_count = min_word_count
        self._style_words = style_words if style_words is not None else DEFAULT_STYLE_WORDS

    def validate(self, prompt: str) -> tuple[bool, list[str]]:
        """Validate a prompt's structural quality.

        Args:
            prompt: The generated image prompt to validate.

        Returns:
            A tuple of (is_valid, issues) where issues is a list of
            human-readable problem descriptions (empty if valid).
        """
        issues: list[str] = []

        if not prompt or not prompt.strip():
            issues.append("prompt is empty")
            return False, issues

        if len(prompt) < 3:
            issues.append("prompt is too short")
            return False, issues

        word_count = len(prompt.split())
        if word_count < self._min_word_count:
            issues.append(f"prompt too short: {word_count} words (minimum {self._min_word_count})")

        prompt_lower = prompt.lower()
        has_style = any(sw in prompt_lower for sw in self._style_words)
        if not has_style:
            issues.append(
                "no style/visual descriptor found "
                "(e.g. 'photorealistic', '4k', 'shot on', 'cinematic')"
            )

        for prefix in _WEAK_PREFIXES:
            if prompt_lower.startswith(prefix):
                issues.append(f"weak prefix '{prefix}' — prompt should be natural language")
                break

        is_valid = len(issues) == 0
        return is_valid, issues
