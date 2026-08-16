"""Background generation worker: run the pipeline and persist a Story."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from factful.agents.writer import strip_claim_tags
from factful.jobstore import JobRecord
from factful.models import Story
from factful.pipeline import DEFAULT_ANGLE, run_pipeline
from factful.report import serialize_report
from factful.runtime import build_runtime


@dataclass(frozen=True)
class GenerationRequest:
    user_id: int
    topic: str
    angle: str | None
    instructions: str | None


GenerationRunner = Callable[[JobRecord, GenerationRequest], None]


def extract_title(markdown: str, fallback: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if next_line and set(next_line) <= {"="} and not stripped.startswith("="):
            return stripped
    return fallback


def run_generation(
    record: JobRecord,
    request: GenerationRequest,
    *,
    sessions: sessionmaker[Session],
    env: Mapping[str, str],
) -> None:
    runtime = build_runtime(dict(env))
    angle = request.angle or DEFAULT_ANGLE
    result = run_pipeline(
        request.topic,
        angle,
        settings=runtime.settings,
        searcher=runtime.searcher,
        fetcher=runtime.fetcher,
        clients=runtime.clients,
        profile=runtime.profile,
        instructions=request.instructions,
        on_progress=record.set_stage,
    )
    markdown = strip_claim_tags(result.state.draft or "")
    with sessions() as db:
        story = Story(
            user_id=request.user_id,
            topic=request.topic,
            angle=angle,
            instructions=request.instructions,
            title=extract_title(markdown, request.topic),
            markdown=markdown,
            score=result.state.score,
            report=json.dumps(serialize_report(result)),
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        record.set_story_id(story.id)


def build_generation_runner(
    *, sessions: sessionmaker[Session], env: Mapping[str, str]
) -> GenerationRunner:
    def run(record: JobRecord, request: GenerationRequest) -> None:
        run_generation(record, request, sessions=sessions, env=env)

    return run
