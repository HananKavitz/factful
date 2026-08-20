"""User settings: analyze, persist, and clear the user's writing style."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from factful.api.deps import get_current_user, get_sessions
from factful.api.schemas import SettingsOut, UpdateStyleRequest
from factful.config import Settings
from factful.llm import ModelRouter, OpenRouterClient
from factful.models import User
from factful.style.analyzer import extract_style
from factful.style.schema import StyleProfile

router = APIRouter()

Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]

StyleExtractor = Callable[[list[str], str], StyleProfile]


def build_style_extractor(*, settings: Settings, env: Mapping[str, str]) -> StyleExtractor:
    api_key = env.get("LLM_API_KEY")
    router = ModelRouter(settings, env=dict(env))

    def extract(samples: list[str], name: str) -> StyleProfile:
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set")
        client = OpenRouterClient(
            model=router.resolve("style"),
            api_key=api_key,
            base_url=settings.llm.base_url,
        )
        return extract_style(samples, name=name, client=client)

    return extract


def _get_profile(db: Session, user_id: int) -> StyleProfile | None:
    user = db.get(User, user_id)
    if user is None or user.style_profile is None:
        return None
    return StyleProfile.model_validate_json(user.style_profile)


@router.get("", response_model=SettingsOut)
def get_settings(
    user: Annotated[User, Depends(get_current_user)], sessions: Sessions
) -> SettingsOut:
    with sessions() as db:
        return SettingsOut(style=_get_profile(db, user.id))


@router.post("/style", response_model=SettingsOut)
def analyze_style(
    body: UpdateStyleRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    sessions: Sessions,
) -> SettingsOut:
    samples = body.samples.strip()
    if not samples:
        raise HTTPException(status_code=422, detail="samples must not be empty")
    extractor: StyleExtractor = request.app.state.style_extractor
    try:
        profile = extractor([samples], "my style")
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"style analysis failed: {exc}") from exc
    with sessions() as db:
        current = db.get(User, user.id)
        if current is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        current.style_profile = profile.model_dump_json()
        db.commit()
    return SettingsOut(style=profile)


@router.delete("/style", status_code=204)
def clear_style(user: Annotated[User, Depends(get_current_user)], sessions: Sessions) -> None:
    with sessions() as db:
        current = db.get(User, user.id)
        if current is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        current.style_profile = None
        db.commit()
