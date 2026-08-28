from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from factful.api.deps import get_current_user, get_sessions
from factful.api.schemas import (
    CreateStoryRequest,
    EditStoryRequest,
    GeneratedNote,
    GenerateNoteRequest,
    JobStatus,
    RenderVideoRequest,
    StoryDetail,
    StorySummary,
    UpdateStoryRequest,
    VideoInfo,
)
from factful.editing import Editor
from factful.generation import GenerationRequest, extract_title
from factful.jobstore import JobStore
from factful.models import Story, User, Video
from factful.notes import NoteGenerator
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
    temperature, top_p = _sampling_for(user.id, sessions)
    job_store.submit(
        record,
        lambda rec: runner(
            rec,
            GenerationRequest(
                user_id=user.id,
                prompt=body.prompt,
                angle=body.angle,
                instructions=body.instructions,
                style_profile=style_profile,
                temperature=temperature,
                top_p=top_p,
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
        if body.prompt is not None:
            story.prompt = body.prompt
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
    temperature, top_p = _sampling_for(user.id, sessions)
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        story.markdown = editor(
            story.markdown, body.prompt, style, temperature=temperature, top_p=top_p
        )
        story.title = extract_title(story.markdown, story.title)
        db.commit()
        db.refresh(story)
        return _to_detail(story)


@router.delete("/{story_id}", status_code=204)
def delete_story(
    story_id: int,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> None:
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        db.delete(story)
        db.commit()


@router.post("/{story_id}/note", response_model=GeneratedNote)
def generate_note(
    story_id: int,
    body: GenerateNoteRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> GeneratedNote:
    generator: NoteGenerator = request.app.state.note_generator
    try:
        note = generator(body.title, body.markdown, body.instructions)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GeneratedNote(note=note)


@router.post("/{story_id}/render-video", status_code=202, response_model=JobStatus)
def render_story_video(
    story_id: int,
    body: RenderVideoRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> JobStatus:
    job_store: JobStore = request.app.state.job_store
    renderer = request.app.state.video_renderer
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
    record = job_store.create(user_id=user.id)
    voice = body.voice or "en-US-AriaNeural"
    job_store.submit(
        record,
        lambda rec: renderer(rec, story_id=story_id, voice=voice, sessions=sessions),
    )
    return JobStatus.model_validate(record.snapshot())


@router.get("/{story_id}/video/{video_id}/file")
def get_video_file(
    story_id: int,
    video_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
):
    with sessions() as db:
        story = _owned_story(db, story_id, user.id)
        if story is None:
            raise HTTPException(status_code=404, detail="story not found")
        video = db.get(Video, video_id)
        if video is None or video.story_id != story_id:
            raise HTTPException(status_code=404, detail="video not found")
        if video.status != "completed":
            raise HTTPException(status_code=404, detail="video is not available")
        if not os.path.exists(video.file_path):
            video.status = "failed"
            video.error_message = "file not found on disk"
            db.commit()
            raise HTTPException(status_code=404, detail="video file not found on disk")
    return FileResponse(video.file_path, media_type="video/mp4")


def _profile_for(user_id: int, sessions: Sessions) -> StyleProfile | None:
    with sessions() as db:
        user = db.get(User, user_id)
        if user is None or user.style_profile is None:
            return None
        return StyleProfile.model_validate_json(user.style_profile)


def _sampling_for(user_id: int, sessions: Sessions) -> tuple[float | None, float | None]:
    with sessions() as db:
        user = db.get(User, user_id)
        if user is None:
            return None, None
        return user.temperature, user.top_p


def _owned_story(db: Session, story_id: int, user_id: int) -> Story | None:
    story = db.get(Story, story_id)
    if story is None or story.user_id != user_id:
        return None
    return story


def _to_summary(story: Story) -> StorySummary:
    return StorySummary(
        id=story.id,
        title=story.title,
        prompt=story.prompt,
        score=story.score,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _to_detail(story: Story) -> StoryDetail:
    return StoryDetail(
        id=story.id,
        title=story.title,
        prompt=story.prompt,
        angle=story.angle,
        instructions=story.instructions,
        markdown=story.markdown,
        score=story.score,
        created_at=story.created_at,
        updated_at=story.updated_at,
        videos=[_video_info(v) for v in story.videos],
    )


def _video_info(video: Video) -> VideoInfo:
    file_exists = os.path.exists(video.file_path) if video.file_path else False
    return VideoInfo(
        id=video.id,
        url=f"/api/stories/{video.story_id}/video/{video.id}/file",
        voice=video.voice,
        duration_seconds=video.duration_seconds,
        file_size_bytes=video.file_size_bytes,
        resolution=video.resolution,
        status=video.status,
        error_message=video.error_message,
        file_exists=file_exists,
        created_at=video.created_at,
    )
