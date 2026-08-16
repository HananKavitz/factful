"""Prompt-driven story editing (synchronous, writer-model only)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from factful.agents.writer import apply_user_edit, strip_claim_tags
from factful.runtime import build_runtime
from factful.style.neutral import neutral_profile
from factful.style.schema import StyleProfile

Editor = Callable[[str, str, StyleProfile | None], str]


def build_editor(*, env: Mapping[str, str]) -> Editor:
    def edit(markdown: str, prompt: str, style: StyleProfile | None = None) -> str:
        runtime = build_runtime(dict(env))
        result = apply_user_edit(
            markdown,
            prompt,
            style or neutral_profile(),
            client=runtime.clients.writer,
            settings=runtime.settings,
        )
        return strip_claim_tags(result.markdown)

    return edit
