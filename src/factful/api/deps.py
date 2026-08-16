from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from factful.models import User


def get_sessions(request: Request) -> sessionmaker[Session]:
    return cast(sessionmaker[Session], request.app.state.sessions)


def get_current_user(
    request: Request,
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> User:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    with sessions() as db:
        user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
