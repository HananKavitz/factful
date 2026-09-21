"""Tests for the VideoService orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from factful.db import build_engine, init_db, session_factory
from factful.models import Story, User
from factful.video.interfaces import (
    Scene,
    VideoOutput,
    VideoRequest,
    VideoScript,
)
from factful.video.music import MusicSelector
from factful.video.service import VideoService, build_video_service
from factful.video.settings import VideoSettings


class _FakeGenerator:
    """A trivial generator that records the script it was handed."""

    def __init__(self) -> None:
        self.received_script: VideoScript | None = None

    def name(self) -> str:
        return "fake"

    async def generate(
        self,
        request: VideoRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
        script: VideoScript | None = None,
    ) -> VideoOutput:
        self.received_script = script
        return VideoOutput(video_path=output_path, resolution="1920x1080")


def _seeded_sessions(tmp_path: Path) -> tuple[Any, int]:
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    sessions = session_factory(engine)
    with sessions() as db:
        user = User(google_sub="sub-1", email="a@example.com", name="Alice")
        db.add(user)
        db.commit()
        story = Story(
            user_id=user.id,
            prompt="Prompt",
            angle="Angle",
            title="Title",
            markdown="# Title\n\nBody.",
            score=90.0,
            report="{}",
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        return sessions, story.id


def _sample_script() -> VideoScript:
    return VideoScript(
        scenes=[
            Scene(
                narration="First scene narration.",
                visual_keywords=["city"],
                shot_type="wide",
                duration_seconds=5,
                need_ai_generation=False,
                ai_confidence=0.0,
            )
        ],
        music_mood="neutral",
        overall_pace="moderate",
    )


class TestVideoServiceScriptPersistence:
    def test_generate_video_writes_script_json(self, tmp_path: Path, monkeypatch: Any) -> None:
        """RED: the generated script is saved to the video directory."""
        monkeypatch.chdir(tmp_path)
        sessions, story_id = _seeded_sessions(tmp_path)

        director = _FakeDirector(_sample_script())
        generator = _FakeGenerator()
        service = VideoService(
            settings=_FakeSettings(default_strategy="fake"),  # type: ignore[arg-type]
            generators={"fake": generator},  # type: ignore[dict-item]
            script_director=director,  # type: ignore[arg-type]
        )

        with sessions() as db:
            story = db.get(Story, story_id)
            assert story is not None
            service.generate_video(story, "voice", sessions, strategy="fake")

        script_path = tmp_path / "videos" / str(story_id) / "script.json"
        assert script_path.exists()
        data = json.loads(script_path.read_text(encoding="utf-8"))
        assert data["scenes"][0]["narration"] == "First scene narration."

    def test_generate_video_passes_script_to_generator(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """RED: the director runs once and its script is handed to the generator."""
        monkeypatch.chdir(tmp_path)
        sessions, story_id = _seeded_sessions(tmp_path)

        director = _FakeDirector(_sample_script())
        generator = _FakeGenerator()
        service = VideoService(
            settings=_FakeSettings(default_strategy="fake"),  # type: ignore[arg-type]
            generators={"fake": generator},  # type: ignore[dict-item]
            script_director=director,  # type: ignore[arg-type]
        )

        with sessions() as db:
            story = db.get(Story, story_id)
            assert story is not None
            service.generate_video(story, "voice", sessions, strategy="fake")

        assert director.analyze_calls == 1
        assert generator.received_script is not None
        assert generator.received_script.scenes[0].narration == "First scene narration."


class _FakeDirector:
    def __init__(self, script: VideoScript) -> None:
        self._script = script
        self.analyze_calls = 0

    def analyze(self, markdown: str, title: str) -> VideoScript:  # noqa: ARG002
        self.analyze_calls += 1
        return self._script


class _FakeSettings:
    def __init__(self, default_strategy: str) -> None:
        self.default_strategy = default_strategy


class TestBuildVideoServiceMusicWiring:
    """The factory threads the music settings into every generator."""

    def test_wires_music_selector_into_all_generators(self) -> None:
        """RED: all strategies must receive the selector, flag, and volume."""
        settings = VideoSettings(music_enabled=True, music_volume=0.42)

        service = build_video_service(
            settings=settings,
            env={},
            llm_api_key="test-key",
            llm_base_url="https://example.test/v1",
        )

        assert set(service._generators) == {"stock", "ai", "hybrid"}
        for name, generator in service._generators.items():
            assert isinstance(generator._music_selector, MusicSelector), name
            assert generator._music_enabled is True, name
            assert generator._music_volume == 0.42, name


class TestBuildVideoServiceSceneLimit:
    """The factory threads the scene cap into the Script Director."""

    def test_director_receives_configured_max_scenes(self) -> None:
        """RED: max_scenes from settings must reach the ScriptDirector."""
        settings = VideoSettings(max_scenes=12)

        service = build_video_service(
            settings=settings,
            env={},
            llm_api_key="test-key",
            llm_base_url="https://example.test/v1",
        )

        assert service._director._max_scenes == 12


def test_video_settings_default_max_scenes() -> None:
    """RED: a default cap keeps scene counts bounded out of the box."""
    assert VideoSettings().max_scenes == 32
