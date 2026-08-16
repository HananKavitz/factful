"""Prompt-driven story editing (synchronous, writer-model only)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from factful.agents.writer import apply_user_edit, strip_claim_tags
from factful.runtime import build_runtime

Editor = Callable[[str, str], str]


def build_editor(*, env: Mapping[str, str]) -> Editor:
    def edit(markdown: str, prompt: str) -> str:
        runtime = build_runtime(dict(env))
        result = apply_user_edit(
            markdown,
            prompt,
            runtime.profile,
            client=runtime.clients.writer,
            settings=runtime.settings,
        )
        return strip_claim_tags(result.markdown)

    return edit
