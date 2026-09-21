"""Script Director: converts markdown article into a structured video script.

Uses a cheap LLM (gpt-4o-mini via OpenRouter) to split the article into
scenes with visual direction and AI-vs-stock classification.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel, Field

from factful.llm.client import ChatClient
from factful.video.exceptions import ScriptError
from factful.video.interfaces import Scene, VideoScript

logger = logging.getLogger(__name__)

_SCRIPT_DIRECTOR_PROMPT = """\
You are a video script director. Given a markdown article, break it into
scenes for a documentary-style video. Each scene covers one coherent topic
from the article.

Cover the ENTIRE article, in order, from the first paragraph to the last.
Do not summarise ahead or stop early: every section must be represented,
and the final scene must cover the article's final paragraph (including its
conclusion, recommendations, or closing remarks). If the article is long,
use more scenes rather than dropping content.
{scene_limit}

For each scene, provide:
1. **narration** - the exact voiceover text (extract 1-3 sentences from the article)
2. **visual_keywords** - 3-5 search/generation keywords for the visuals
3. **shot_type** - one of: "establishing", "wide", "close_up", "aerial", "abstract"
4. **duration_seconds** - how long this scene runs (5-15 seconds)
5. **need_ai_generation** - whether this scene ABSOLUTELY NEEDS AI video generation
   because the concept is too specific/abstract for generic stock footage,
   OR because it involves data/charts/graphs, OR because it depicts a
   specific technical object (quantum computer, fusion reactor, DNA, etc.)
6. **ai_confidence** - 0.0-1.0 confidence that AI gen is truly necessary

Set need_ai_generation=False for generic visuals: cities, nature, people,
offices, technology, industry, etc.

Also provide:
- music_mood: one of "neutral", "inspirational", "analytical", "urgent", "calm"
- overall_pace: one of "slow_documentary", "moderate", "fast_explainer"

Article title: {title}
Article:
{markdown}
"""


def _scene_limit_instruction(max_scenes: int | None) -> str:
    """Prompt clause that caps the scene count, or an empty string."""
    if max_scenes is None:
        return ""
    return (
        f"Produce at most {max_scenes} scenes in total. If the article is long, "
        "make each scene cover more of the article (more sentences) rather than "
        "exceeding this limit."
    )


def merge_scenes_to_limit(scenes: list[Scene], max_scenes: int) -> list[Scene]:
    """Fuse adjacent scenes until at most *max_scenes* remain.

    Full-article coverage is preserved: merging concatenates narration and
    never drops a scene. Scenes are grouped greedily toward an even share of
    the total duration so a shorter tail is not swallowed into one long scene.

    Args:
        scenes: Scenes in article order.
        max_scenes: Upper bound on the returned scene count (>= 1).

    Returns:
        A new list of scenes, in order, with length <= *max_scenes*.

    Raises:
        ValueError: if *max_scenes* is less than 1.
    """
    if max_scenes < 1:
        raise ValueError(f"max_scenes must be >= 1, got {max_scenes}")
    if len(scenes) <= max_scenes:
        return list(scenes)

    target_duration = sum(scene.duration_seconds for scene in scenes) / max_scenes
    groups: list[list[Scene]] = []
    current: list[Scene] = []
    current_duration = 0
    for position, scene in enumerate(scenes):
        current.append(scene)
        current_duration += scene.duration_seconds
        scenes_left = len(scenes) - position - 1
        groups_left = max_scenes - len(groups)
        if (
            groups_left > 1
            and current_duration >= target_duration
            and scenes_left >= groups_left - 1
        ):
            groups.append(current)
            current = []
            current_duration = 0
    if current:
        groups.append(current)
    return [_merge_group(group) for group in groups]


def _merge_group(group: list[Scene]) -> Scene:
    """Combine consecutive scenes into a single scene."""
    keywords: list[str] = []
    for scene in group:
        for keyword in scene.visual_keywords:
            if keyword not in keywords:
                keywords.append(keyword)
    return Scene(
        narration=" ".join(scene.narration for scene in group),
        visual_keywords=keywords[:8],
        shot_type=group[0].shot_type,
        duration_seconds=sum(scene.duration_seconds for scene in group),
        need_ai_generation=any(scene.need_ai_generation for scene in group),
        ai_confidence=max(scene.ai_confidence for scene in group),
    )


class SceneOut(BaseModel):
    narration: str = Field(min_length=1)
    visual_keywords: list[str] = Field(min_length=1, max_length=8)
    shot_type: str = Field(pattern=r"^(establishing|wide|close_up|aerial|abstract)$")
    duration_seconds: int = Field(ge=3, le=20)
    need_ai_generation: bool = False
    ai_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ScriptOut(BaseModel):
    scenes: list[SceneOut] = Field(min_length=1)
    music_mood: str = Field(pattern=r"^(neutral|inspirational|analytical|urgent|calm)$")
    overall_pace: str = Field(pattern=r"^(slow_documentary|moderate|fast_explainer)$")


class ScriptDirector:
    """Convert article markdown into a structured VideoScript.

    Args:
        client: An OpenRouterClient (or any ChatClient) configured with
            a cheap model like gpt-4o-mini.
        max_scenes: Optional upper bound on the scene count. Over-limit
            scripts are merged, never truncated.
        cancel_check: Optional callable returning True if cancelled.
    """

    def __init__(
        self,
        *,
        client: ChatClient,
        max_scenes: int | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self._client = client
        self._max_scenes = max_scenes
        self._cancel_check = cancel_check

    def analyze(self, markdown: str, title: str) -> VideoScript:
        """Run the LLM and return a structured VideoScript.

        Args:
            markdown: The full article markdown.
            title: The article title.

        Returns:
            A VideoScript with scenes and metadata.

        Raises:
            ScriptError: if the LLM fails to produce a valid script.
        """
        if not markdown.strip():
            raise ScriptError("cannot analyze empty article")

        prompt = _SCRIPT_DIRECTOR_PROMPT.format(
            title=title,
            markdown=markdown,
            scene_limit=_scene_limit_instruction(self._max_scenes),
        )

        if self._cancel_check is not None and self._cancel_check():
            raise ScriptError("video generation was cancelled")

        try:
            raw = self._client.chat_completion(
                prompt=prompt,
                schema=ScriptOut,
                temperature=0.3,
            )
        except Exception as exc:
            raise ScriptError(f"Script Director LLM failed: {exc}") from exc

        if not isinstance(raw, ScriptOut) or not raw.scenes:
            raise ScriptError("Script Director returned an empty script")

        scenes = [
            Scene(
                narration=s.narration,
                visual_keywords=s.visual_keywords,
                shot_type=s.shot_type,
                duration_seconds=s.duration_seconds,
                need_ai_generation=s.need_ai_generation,
                ai_confidence=s.ai_confidence,
            )
            for s in raw.scenes
        ]

        if self._max_scenes is not None:
            scenes = merge_scenes_to_limit(scenes, self._max_scenes)

        return VideoScript(
            scenes=scenes,
            music_mood=raw.music_mood,
            overall_pace=raw.overall_pace,
        )
