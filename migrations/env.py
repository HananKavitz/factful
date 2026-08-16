"""Alembic migration environment.

Connects using the same engine resolution as the application
(`factful.db.build_engine_config`) so local SQLite and Turso/libsql databases
are migrated identically. When driven programmatically from `init_db`, the
already-built engine is supplied via `config.attributes["engine"]`.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine

from factful.db import Base, build_engine_config

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url_and_args() -> tuple[str, dict[str, str]]:
    url = os.environ.get("DATABASE_URL", "sqlite:///./factful.db")
    return build_engine_config(url, env=dict(os.environ))


def run_migrations_offline() -> None:
    url, _ = _resolve_url_and_args()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = config.attributes.get("engine")
    if engine is None:
        url, kwargs = _resolve_url_and_args()
        engine = create_engine(url, **kwargs)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
