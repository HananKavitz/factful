"""On-demand Substack Note generation from a story's title and markdown."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, Field


class NoteOutput(BaseModel):
    """Schema for the LLM response â€” a short Substack Note."""

    note: str = Field(min_length=1, max_length=2000)


_NOTE_PROMPT = """
You are an expert Substack writer who also writes great promotional Notes.

Given the article TITLE and MARKDOWN below, write a short, punchy Substack Note
that promotes the article. A Substack Note is a brief social-media-style post
that hooks readers and makes them want to read the full piece.

Rules:
- 1-3 sentences maximum.
- Start with a hook â€” something surprising, provocative, or evocative.
- Include the article's core insight or angle.
- End with a call to action like "Read more" or "Full story below" â€” do NOT
  include an actual URL because the author will add it.
- Match the tone of the article (serious, witty, urgent, reflective, etc.).
- Do NOT use hashtags, markdown formatting, or bullet points.
- Keep it raw text â€” the author will edit it before posting.
- Do NOT write about the article itself (e.g. "in this article..."). Instead,
  write directly about the topic as if you're the author sharing a thought.
{instructions_block}
Article title: {title}

Article body:
{markdown}

Return a JSON object with a single field "note" containing the Substack Note text.
""".strip()


def _instructions_block(instructions: str | None) -> str:
    if not instructions or not instructions.strip():
        return ""
    return f"Author's additional instructions (follow these carefully):\n{instructions.strip()}"


class NoteGenerator(Protocol):
    def __call__(self, title: str, markdown: str, instructions: str | None = None) -> str: ...


def build_note_generator(*, env: Mapping[str, str]) -> NoteGenerator:
    """Build a lazy note generator.

    The runtime (which requires API keys) is created on the first call, not at
    factory time, so that app creation doesn't fail in tests or contexts where
    the LLM is never invoked.
    """
    runtime: object = None  # PipelineRuntime â€” delayed import

    def generate(title: str, markdown: str, instructions: str | None = None) -> str:
        nonlocal runtime
        if runtime is None:
            from factful.runtime import build_runtime

            runtime = build_runtime(dict(env))
        prompt = _NOTE_PROMPT.format(
            title=title,
            markdown=markdown,
            instructions_block=_instructions_block(instructions),
        )
        result = runtime.clients.writer.chat_completion(  # type: ignore[attr-defined]
            prompt=prompt,
            schema=NoteOutput,
            temperature=0.7,
            top_p=0.9,
        )
        if not isinstance(result, NoteOutput):
            raise TypeError(f"expected NoteOutput, got {type(result).__name__}")
        return result.note

    return generate
