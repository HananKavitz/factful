"""Tests for the Script Director: article markdown → VideoScript."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from factful.llm.client import ChatClient
from factful.video.exceptions import ScriptError
from factful.video.interfaces import Scene, VideoScript
from factful.video.script_director import (
    SceneOut,
    ScriptDirector,
    ScriptOut,
    merge_scenes_to_limit,
)


class _FakeClient(ChatClient):
    """A fake ChatClient that returns a predetermined ScriptOut."""

    def __init__(self, script_out: ScriptOut | None = None) -> None:
        self._script_out = script_out
        self.last_prompt: str | None = None
        self.last_schema: type[BaseModel] | None = None

    def chat_completion(
        self,
        *,
        prompt: str,
        schema: type[BaseModel],
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> BaseModel:
        self.last_prompt = prompt
        self.last_schema = schema
        if self._script_out is None:
            msg = "LLM call failed"
            raise RuntimeError(msg)
        return self._script_out


class _FailingClient(ChatClient):
    """A fake ChatClient that always raises."""

    def chat_completion(
        self,
        *,
        prompt: str,
        schema: type[BaseModel],
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> BaseModel:
        msg = "API timeout"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_script() -> ScriptOut:
    return ScriptOut(
        scenes=[
            SceneOut(
                narration="First scene narration.",
                visual_keywords=["sunset", "ocean"],
                shot_type="wide",
                duration_seconds=8,
                need_ai_generation=False,
                ai_confidence=0.0,
            ),
            SceneOut(
                narration="Second scene narration.",
                visual_keywords=["quantum", "computer"],
                shot_type="close_up",
                duration_seconds=10,
                need_ai_generation=True,
                ai_confidence=0.95,
            ),
        ],
        music_mood="calm",
        overall_pace="moderate",
    )


SAMPLE_MARKDOWN = "# The Future\n\nQuantum computing is here."
SAMPLE_TITLE = "The Future of Computing"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScriptDirectorAnalyze:
    """ScriptDirector.analyze() behaviour."""

    def test_empty_markdown_raises(self) -> None:
        """RED: empty article markdown should raise ScriptError immediately."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        with pytest.raises(ScriptError, match="cannot analyze empty article"):
            director.analyze(markdown="", title=SAMPLE_TITLE)

    def test_empty_whitespace_markdown_raises(self) -> None:
        """RED: whitespace-only markdown should raise ScriptError."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        with pytest.raises(ScriptError, match="cannot analyze empty article"):
            director.analyze(markdown="   \n  \t  ", title=SAMPLE_TITLE)

    def test_llm_failure_raises_script_error(self) -> None:
        """RED: if the underlying LLM raises, we wrap it in ScriptError."""
        client = _FailingClient()
        director = ScriptDirector(client=client)

        with pytest.raises(ScriptError, match="Script Director LLM failed"):
            director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

    def test_llm_empty_scenes_raises(self) -> None:
        """RED: an LLM response with zero scenes should raise."""
        empty = ScriptOut.model_construct(scenes=[], music_mood="neutral", overall_pace="moderate")
        client = _FakeClient(empty)
        director = ScriptDirector(client=client)

        with pytest.raises(ScriptError, match="returned an empty script"):
            director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

    def test_returns_video_script_with_correct_structure(self) -> None:
        """RED: valid LLM response produces a correctly structured VideoScript."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        result = director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert isinstance(result, VideoScript)
        assert len(result.scenes) == 2
        assert result.music_mood == "calm"
        assert result.overall_pace == "moderate"

    def test_scene_fields_are_preserved(self) -> None:
        """RED: each Scene in the result carries the correct fields."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        result = director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        scene = result.scenes[0]
        assert isinstance(scene, Scene)
        assert scene.narration == "First scene narration."
        assert scene.visual_keywords == ["sunset", "ocean"]
        assert scene.shot_type == "wide"
        assert scene.duration_seconds == 8
        assert scene.need_ai_generation is False
        assert scene.ai_confidence == 0.0

    def test_ai_scene_fields(self) -> None:
        """RED: the second scene has AI generation enabled."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        result = director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        scene = result.scenes[1]
        assert scene.need_ai_generation is True
        assert scene.ai_confidence == 0.95
        assert scene.visual_keywords == ["quantum", "computer"]
        assert scene.shot_type == "close_up"

    def test_prompt_includes_title_and_markdown(self) -> None:
        """RED: the prompt sent to the LLM should contain the title and article."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert client.last_prompt is not None
        assert SAMPLE_TITLE in client.last_prompt
        assert SAMPLE_MARKDOWN in client.last_prompt

    def test_prompt_requires_full_article_coverage(self) -> None:
        """RED: the prompt must demand end-to-end coverage so the model
        cannot stop before the article's final paragraph."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        prompt = (client.last_prompt or "").lower()
        assert "entire article" in prompt
        assert "in order" in prompt
        assert "final paragraph" in prompt

    def test_passes_script_out_schema(self) -> None:
        """RED: the director requests ScriptOut as the schema."""
        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client)

        director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert client.last_schema is ScriptOut

    def test_cancel_check_stops_execution(self) -> None:
        """RED: a cancelled job should not call the LLM."""

        def _cancel() -> bool:
            return True

        client = _FakeClient(_sample_script())
        director = ScriptDirector(client=client, cancel_check=_cancel)

        with pytest.raises(ScriptError, match="cancelled"):
            director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)
        assert client.last_prompt is None  # LLM should NOT have been called


class TestScriptDirectorSceneLimit:
    """The director honours a maximum scene count instead of over-splitting."""

    def _script_with(self, count: int, duration: int = 10) -> ScriptOut:
        return ScriptOut(
            scenes=[
                SceneOut(
                    narration=f"Scene {i} narration.",
                    visual_keywords=[f"keyword{i}"],
                    shot_type="wide",
                    duration_seconds=duration,
                    need_ai_generation=False,
                    ai_confidence=0.0,
                )
                for i in range(count)
            ],
            music_mood="neutral",
            overall_pace="moderate",
        )

    def test_prompt_states_the_scene_limit_when_configured(self) -> None:
        """RED: the model must be told the cap so it can pace itself."""
        client = _FakeClient(self._script_with(2))
        director = ScriptDirector(client=client, max_scenes=7)

        director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert "at most 7 scenes" in (client.last_prompt or "")

    def test_prompt_omits_scene_limit_when_unset(self) -> None:
        """RED: no cap configured means no cap text in the prompt."""
        client = _FakeClient(self._script_with(2))
        director = ScriptDirector(client=client)

        director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert "at most" not in (client.last_prompt or "").lower()

    def test_scenes_over_limit_are_merged_not_dropped(self) -> None:
        """RED: over-limit scripts keep every narration, fused into fewer scenes."""
        client = _FakeClient(self._script_with(6, duration=10))
        director = ScriptDirector(client=client, max_scenes=2)

        result = director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert len(result.scenes) <= 2
        merged_narration = " ".join(scene.narration for scene in result.scenes)
        for i in range(6):
            assert f"Scene {i} narration." in merged_narration
        assert sum(scene.duration_seconds for scene in result.scenes) == 60

    def test_scenes_within_limit_are_untouched(self) -> None:
        """RED: a script at or under the cap passes through unchanged."""
        client = _FakeClient(self._script_with(3))
        director = ScriptDirector(client=client, max_scenes=5)

        result = director.analyze(markdown=SAMPLE_MARKDOWN, title=SAMPLE_TITLE)

        assert [scene.narration for scene in result.scenes] == [
            "Scene 0 narration.",
            "Scene 1 narration.",
            "Scene 2 narration.",
        ]


class TestMergeScenesToLimit:
    """Pure helper: fuse adjacent scenes down to a maximum count."""

    def _scene(self, idx: int, duration: int = 10) -> Scene:
        return Scene(
            narration=f"N{idx}.",
            visual_keywords=[f"k{idx}"],
            shot_type="wide",
            duration_seconds=duration,
        )

    def test_merges_to_at_most_the_limit(self) -> None:
        """RED: ten scenes with a limit of three must yield exactly three."""
        merged = merge_scenes_to_limit([self._scene(i) for i in range(10)], 3)
        assert len(merged) == 3

    def test_preserves_every_narration_in_order(self) -> None:
        """RED: merging never drops narration and keeps article order."""
        scenes = [self._scene(i, duration=5) for i in range(9)]
        merged = merge_scenes_to_limit(scenes, 4)
        assert " ".join(s.narration for s in merged) == " ".join(s.narration for s in scenes)
        assert sum(s.duration_seconds for s in merged) == 45

    def test_under_limit_returns_a_copy(self) -> None:
        """RED: no merge needed returns an equal but distinct list."""
        scenes = [self._scene(0)]
        merged = merge_scenes_to_limit(scenes, 5)
        assert merged == scenes
        assert merged is not scenes

    def test_merges_keywords_and_ai_flags(self) -> None:
        """RED: fused scenes union keywords and promote the AI signal."""
        scenes = [
            Scene(
                narration="a",
                visual_keywords=["x", "y"],
                duration_seconds=5,
                need_ai_generation=False,
                ai_confidence=0.1,
            ),
            Scene(
                narration="b",
                visual_keywords=["y", "z"],
                duration_seconds=5,
                need_ai_generation=True,
                ai_confidence=0.9,
            ),
        ]
        merged = merge_scenes_to_limit(scenes, 1)
        assert len(merged) == 1
        assert merged[0].visual_keywords == ["x", "y", "z"]
        assert merged[0].need_ai_generation is True
        assert merged[0].ai_confidence == 0.9

    def test_invalid_limit_raises(self) -> None:
        """RED: a non-positive limit is a programmer error."""
        with pytest.raises(ValueError, match="max_scenes"):
            merge_scenes_to_limit([self._scene(0)], 0)
