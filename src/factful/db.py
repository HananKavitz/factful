"""Database engine, session factory, and declarative base."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def build_engine_config(
    url: str, env: Mapping[str, str] | None = None
) -> tuple[str, dict[str, Any]]:
    """Resolve a database URL into an engine URL plus connect args (pure)."""
    env = env or {}
    if url.startswith("sqlite+libsql://") or url.startswith("libsql://"):
        token = env.get("TURSO_AUTH_TOKEN")
        if not token:
            raise ValueError("TURSO_AUTH_TOKEN is required to connect to a libsql database")
        if url.startswith("sqlite+libsql://"):
            driver_url = url
        else:
            driver_url = f"sqlite+libsql://{url.removeprefix('libsql://')}?secure=true"
        return driver_url, {"auth_token": token}
    return url, {}


def build_engine(url: str, env: Mapping[str, str] | None = None) -> Engine:
    resolved_url, connect_args = build_engine_config(url, env)
    if resolved_url.startswith("sqlite+libsql://"):
        if importlib.util.find_spec("sqlalchemy_libsql") is None:
            raise ImportError(
                "sqlalchemy-libsql is required for libsql databases; "
                "install with `uv sync --extra turso`"
            )
        return create_engine(resolved_url, connect_args=connect_args)
    if resolved_url.startswith("sqlite"):
        kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if resolved_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(resolved_url, **kwargs)
        _enable_sqlite_foreign_keys(engine)
        return engine
    return create_engine(resolved_url, **connect_args)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    if _is_ephemeral(engine):
        Base.metadata.create_all(engine)
        return
    _upgrade_to_head(engine)


def _is_ephemeral(engine: Engine) -> bool:
    url = engine.url
    if url.drivername != "sqlite":
        return False
    return url.database in (None, "", ":memory:")


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


def _upgrade_to_head(engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(_migrations_dir()))
    config.attributes["engine"] = engine
    command.upgrade(config, "head")
