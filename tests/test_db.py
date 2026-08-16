import pytest

from factful.db import build_engine, build_engine_config, init_db, session_factory
from factful.models import Story, User


def test_engine_config_default_sqlite_passthrough() -> None:
    url, kwargs = build_engine_config("sqlite:///./factful.db")
    assert url == "sqlite:///./factful.db"
    assert kwargs == {}


def test_engine_config_turso_remote() -> None:
    url, kwargs = build_engine_config("libsql://my-db.turso.io", env={"TURSO_AUTH_TOKEN": "t-123"})
    assert url == "sqlite+libsql://my-db.turso.io?secure=true"
    assert kwargs == {"auth_token": "t-123"}


def test_engine_config_turso_already_prefixed() -> None:
    url, kwargs = build_engine_config(
        "sqlite+libsql://my-db.turso.io", env={"TURSO_AUTH_TOKEN": "t-123"}
    )
    assert url == "sqlite+libsql://my-db.turso.io"
    assert kwargs == {"auth_token": "t-123"}


def test_engine_config_turso_requires_token() -> None:
    with pytest.raises(ValueError, match="TURSO_AUTH_TOKEN"):
        build_engine_config("libsql://my-db.turso.io", env={})


def test_build_engine_sqlite_memory_uses_static_pool() -> None:
    engine = build_engine("sqlite:///:memory:")
    assert type(engine.pool).__name__ == "StaticPool"


def test_init_db_creates_tables() -> None:
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    from sqlalchemy import inspect

    assert set(inspect(engine).get_table_names()) == {"users", "stories"}


def test_init_db_applies_migrations_to_file_db(tmp_path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    init_db(engine)
    from sqlalchemy import inspect

    inspector = inspect(engine)
    assert {"users", "stories", "alembic_version"} <= set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("users")}
    assert "style_profile" in columns


def test_init_db_file_backed_is_idempotent(tmp_path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'twice.db'}")
    init_db(engine)
    init_db(engine)
    from sqlalchemy import inspect

    assert {"users", "stories", "alembic_version"} <= set(inspect(engine).get_table_names())


def test_session_factory_roundtrip() -> None:
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    sessions = session_factory(engine)
    with sessions() as db:
        user = User(google_sub="sub-1", email="a@example.com", name="Alice")
        db.add(user)
        db.commit()
        story = Story(
            user_id=user.id,
            topic="Chips",
            angle="supply risk",
            title="Chips",
            markdown="# Chips\n\nBody.",
            score=88.5,
            report='{"passes": []}',
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        assert story.id is not None
        assert story.created_at is not None
        assert story.updated_at is not None
        assert story.user.name == "Alice"
