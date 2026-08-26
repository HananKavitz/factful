"""Prompt-driven story editing (synchronous, writer-model only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from factful.agents.writer import apply_user_edit, strip_claim_tags
from factful.runtime import build_runtime
from factful.style.neutral import neutral_profile
from factful.style.schema import StyleProfile


class Editor(Protocol):
    def __call__(
        self,
        markdown: str,
        prompt: str,
        style: StyleProfile | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str: ...


def build_editor(*, env: Mapping[str, str]) -> Editor:
    def edit(
        markdown: str,
        prompt: str,
        style: StyleProfile | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        runtime = build_runtime(dict(env))
        result = apply_user_edit(
            markdown,
            prompt,
            style or neutral_profile(),
            client=runtime.clients.writer,
            settings=runtime.settings,
            temperature=temperature,
            top_p=top_p,
        )
        return strip_claim_tags(result.markdown)

    return edit
