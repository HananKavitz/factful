from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select

from factful.config import Settings
from factful.db import build_engine, init_db, session_factory
from factful.generation import DEFAULT_ANGLE, GenerationRequest, extract_title, run_generation
from factful.jobstore import JobRecord
from factful.models import Story, User
from factful.pipeline import PipelineResult
from factful.schemas import Citation, CritiqueReport, FactVerdict, SourceBundle
from factful.state import PipelineState


def make_result(*, draft: str, score: int = 90) -> PipelineResult:
    citation = Citation(
        claim_id="c1",
        claim="Revenue hit $4B in 2024",
        source_url="https://example.com/report",
        source_title="Annual Report",
        publisher="example.com",
        publish_date="2024-01-01",
        key_stat="$4B",
        quote_snippet="Revenue hit $4B in 2024.",
        passage_ref="para-2",
        retrieved_at="2024-01-02T00:00:00Z",
    )
    state = PipelineState(
        topic="Topic",
        angle="Angle",
        source_bundle=SourceBundle(topic="Topic", angle="Angle", citations=[citation]),
    )
    state.add_verdict(FactVerdict(claim_id="c1", status="verified", confidence=0.9, reason="ok"))
    state.add_critique(CritiqueReport(score=score, issues=[], verdict="pass"))
    state.record_pass(score=score, draft=draft)
    return PipelineResult(state=state, decision="publish", reason="hard gate passed", unresolved=[])


class TestExtractTitle:
    def test_first_heading_wins(self) -> None:
        assert extract_title("# The Big Story\n\nbody", "fallback") == "The Big Story"

    def test_setext_heading_wins(self) -> None:
        markdown = "Leading prose\n=============\n\n## Section\n\nbody"
        assert extract_title(markdown, "fallback") == "Leading prose"

    def test_fallback_when_no_heading(self) -> None:
        assert extract_title("just body text", "fallback") == "fallback"


@dataclass(frozen=True)
class RuntimeStub:
    settings: Settings
    searcher: object
    fetcher: object
    clients: object
    profile: object


def make_runtime_stub() -> RuntimeStub:
    return RuntimeStub(
        settings=Settings(),
        searcher=object(),
        fetcher=object(),
        clients=object(),
        profile=object(),
    )


def fake_pipeline(calls: list[str], on_progress) -> PipelineResult:
    if on_progress:
        for stage in ["writing draft", "fact-checking", "critiquing"]:
            on_progress(stage)
            calls.append(stage)
    return make_result(draft="[[c1]]\n# The Big Story\n\nbody")


class TestRunGeneration:
    def test_persists_story_and_updates_job(self, tmp_path, monkeypatch) -> None:
        engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
        init_db(engine)
        sessions = session_factory(engine)

        with sessions() as db:
            user = User(
                id=7,
                google_sub="mock:alice@example.com",
                email="alice@example.com",
                name="Alice",
            )
            db.add(user)
            db.commit()

        monkeypatch.setattr("factful.generation.build_runtime", lambda env: make_runtime_stub())
        calls: list[str] = []
        monkeypatch.setattr(
            "factful.generation.run_pipeline",
            lambda *args, **kwargs: fake_pipeline(calls, kwargs.get("on_progress")),
        )

        record = JobRecord("job-1", user_id=7)
        run_generation(
            record,
            GenerationRequest(user_id=7, topic="Topic", angle=None, instructions="keep it short"),
            sessions=sessions,
            env={"LLM_API_KEY": "k", "TAVILY_API_KEY": "t"},
        )

        snapshot = record.snapshot()
        assert snapshot["status"] == "done"
        assert calls == ["writing draft", "fact-checking", "critiquing"]

        with sessions() as db:
            story = db.scalars(select(Story)).one()
            assert story.user_id == 7
            assert story.topic == "Topic"
            assert story.angle == DEFAULT_ANGLE
            assert story.instructions == "keep it short"
            assert story.title == "The Big Story"
            assert story.markdown == "# The Big Story\n\nbody"
            assert story.score == 90
            report = json.loads(story.report)
            assert report["decision"] == "publish"
            assert snapshot["story_id"] == story.id

    def test_error_propagates_and_persists_no_story(self, tmp_path, monkeypatch) -> None:
        engine = build_engine(f"sqlite:///{tmp_path / 'err.db'}")
        init_db(engine)
        sessions = session_factory(engine)

        def boom(*args, **kwargs) -> PipelineResult:
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr("factful.generation.run_pipeline", boom)
        monkeypatch.setattr("factful.generation.build_runtime", lambda env: make_runtime_stub())

        record = JobRecord("job-2", user_id=7)
        try:
            run_generation(
                record,
                GenerationRequest(user_id=7, topic="T", angle="A", instructions=None),
                sessions=sessions,
                env={},
            )
        except RuntimeError:
            pass

        with sessions() as db:
            assert db.scalars(select(Story)).all() == []
