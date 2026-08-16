from __future__ import annotations

from typing import Annotated, cast

from authlib.integrations.base_client import MismatchingStateError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import RedirectResponse, Response

from factful.api.deps import get_current_user, get_sessions
from factful.api.schemas import MockLoginRequest, UserOut
from factful.models import User

router = APIRouter()

Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]


def _build_google_client(request: Request) -> StarletteOAuth2App:
    web = request.app.state.web
    if not web.google_client_id or not web.google_client_secret:
        raise HTTPException(status_code=500, detail="google oauth is not configured")
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=web.google_client_id,
        client_secret=web.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.create_client("google")


@router.get("/login")
async def google_login(request: Request) -> Response:
    web = request.app.state.web
    if web.auth_mode != "google":
        raise HTTPException(status_code=403, detail="google auth is disabled")
    client = _build_google_client(request)
    redirect_uri = str(request.url_for("google_callback"))
    return cast(Response, await client.authorize_redirect(request, redirect_uri))


@router.get("/callback", name="google_callback")
async def google_callback(request: Request, sessions: Sessions) -> RedirectResponse:
    web = request.app.state.web
    if web.auth_mode != "google":
        raise HTTPException(status_code=403, detail="google auth is disabled")
    client = _build_google_client(request)
    try:
        token = await client.authorize_access_token(request)
    except MismatchingStateError as exc:
        raise HTTPException(status_code=400, detail="oauth state mismatch") from exc
    userinfo = await client.userinfo(token=token)
    google_sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    if not google_sub or not email:
        raise HTTPException(status_code=400, detail="google account is missing profile or email")
    with sessions() as db:
        user = db.scalars(select(User).where(User.google_sub == google_sub)).first()
        if user is None:
            user = User(
                google_sub=google_sub,
                email=email,
                name=userinfo.get("name") or email.split("@")[0],
                picture=userinfo.get("picture"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=303)


@router.post("/mock", response_model=UserOut)
def mock_login(
    body: MockLoginRequest,
    request: Request,
    sessions: Sessions,
) -> UserOut:
    web = request.app.state.web
    if web.auth_mode != "mock":
        raise HTTPException(status_code=403, detail="mock auth is disabled")
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="email is required")
    with sessions() as db:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(
                google_sub=f"mock:{email}",
                email=email,
                name=body.name or email.split("@")[0],
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id
        user_name = user.name
        user_picture = user.picture
    request.session["user_id"] = user_id
    return UserOut(id=user_id, email=email, name=user_name, picture=user_picture)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, picture=user.picture)


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}
