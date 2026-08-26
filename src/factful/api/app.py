from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from factful.api import auth, jobs, stories
from factful.api.settings import build_style_extractor
from factful.api.settings import router as settings_router
from factful.config import Settings, load_settings, load_web_settings
from factful.db import build_engine, init_db, session_factory
from factful.editing import build_editor
from factful.generation import build_generation_runner
from factful.jobstore import JobStore
from factful.notes import build_note_generator
from factful.static import default_frontend_dist, mount_frontend


def create_app(
    settings: Settings | None = None,
    env: Mapping[str, str] | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    if env is None:
        load_dotenv()
        env = dict(os.environ)
    settings = settings or load_settings()
    web = load_web_settings(settings, env)
    engine = build_engine(web.database_url, env)
    init_db(engine)
    sessions = session_factory(engine)
    job_store = JobStore()
    generation_runner = build_generation_runner(sessions=sessions, env=env)
    editor = build_editor(env=env)

    app = FastAPI(title="factful")
    app.add_middleware(
        SessionMiddleware,
        secret_key=web.session_secret,
        session_cookie="factful_session",
    )
    app.state.settings = settings
    app.state.web = web
    app.state.sessions = sessions
    app.state.job_store = job_store
    app.state.generation_runner = generation_runner
    app.state.editor = editor
    app.state.style_extractor = build_style_extractor(settings=settings, env=dict(env))
    app.state.note_generator = build_note_generator(env=env)
    app.state.env = dict(env)
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(stories.router, prefix="/api/stories")
    app.include_router(jobs.router, prefix="/api/jobs")
    app.include_router(settings_router, prefix="/api/settings")
    if frontend_dist is None and env.get("FRONTEND_DIST_DIR"):
        frontend_dist = Path(str(env["FRONTEND_DIST_DIR"]))
    mount_frontend(app, frontend_dist or default_frontend_dist())
    return app
