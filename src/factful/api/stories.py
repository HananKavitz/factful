from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from factful.api.deps import get_current_user, get_sessions
from factful.api.schemas import (
    CreateStoryRequest,
    EditStoryRequest,
    JobStatus,
    StoryDetail,
    StorySummary,
    UpdateStoryRequest,
)
from factful.editing import Editor
from factful.generation import GenerationRequest, extract_title
from factful.jobstore import JobStore
from factful.models import Story, User
from factful.style.schema import StyleProfile

router = APIRouter()

Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]


@router.get("", response_model=list[StorySummary])
def list_stories(
    user: Annotated[User, Depends(get_current_user)], sessions: Sessions
) -> list[StorySummary]:
    with sessions() as db:
        stories = db.scalars(
            select(Story)
            .where(Story.user_id == user.id)
            .order_by(Story.created_at.desc(), Story.id.desc())
        ).all()
        return [_to_summary(story) for story in stories]


@router.post("", status_code=202, response_model=JobStatus)
def create_story(
    body: CreateStoryRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> JobStatus:
    job_store: JobStore = request.app.state.job_store
    runner = request.app.state.generation_runner
    record = job_store.create(user_id=user.id)
    style_profile = _profile_for(user.id, sessions)
    job_store.submit(
        record,
        lambda rec: runner(
            rec,
            GenerationRequest(
                user_id=user.id,
                topic=body.topic,
                angle=body.angle,
                instructions=body.instructions,
                style_profile=style_profile,
            ),
        ),
    )
    return JobStatus.model_validate(record.snapshot())


@router.get("/{story_id}", response_model=StoryDetail)
def get_story(
    story_id: int,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> StoryDetail:
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        return _to_detail(story)


@router.put("/{story_id}", response_model=StoryDetail)
def update_story(
    story_id: int,
    body: UpdateStoryRequest,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> StoryDetail:
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        if body.title is not None:
            story.title = body.title
        if body.markdown is not None:
            story.markdown = body.markdown
        db.commit()
        db.refresh(story)
        return _to_detail(story)


@router.post("/{story_id}/edit", response_model=StoryDetail)
def edit_story(
    story_id: int,
    body: EditStoryRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> StoryDetail:
    editor: Editor = request.app.state.editor
    style = _profile_for(user.id, sessions)
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        story.markdown = editor(story.markdown, body.prompt, style)
        story.title = extract_title(story.markdown, story.title)
        db.commit()
        db.refresh(story)
        return _to_detail(story)


def _profile_for(user_id: int, sessions: Sessions) -> StyleProfile | None:
    with sessions() as db:
        user = db.get(User, user_id)
        if user is None or user.style_profile is None:
            return None
        return StyleProfile.model_validate_json(user.style_profile)


def _owned_story(db: Session, story_id: int, user_id: int) -> Story | None:
    story = db.get(Story, story_id)
    if story is None or story.user_id != user_id:
        return None
    return story


def _to_summary(story: Story) -> StorySummary:
    return StorySummary(
        id=story.id,
        title=story.title,
        topic=story.topic,
        score=story.score,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _to_detail(story: Story) -> StoryDetail:
    return StoryDetail(
        id=story.id,
        title=story.title,
        topic=story.topic,
        angle=story.angle,
        instructions=story.instructions,
        markdown=story.markdown,
        score=story.score,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )
