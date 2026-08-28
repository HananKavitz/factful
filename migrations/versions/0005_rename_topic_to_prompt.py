"""rename stories.topic to stories.prompt

Revision ID: 0005_rename_topic_to_prompt
Revises: 0004_add_videos_table
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_rename_topic_to_prompt"
down_revision: str | None = "0004_add_videos_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stories") as batch:
        batch.alter_column("topic", new_column_name="prompt")


def downgrade() -> None:
    with op.batch_alter_table("stories") as batch:
        batch.alter_column("prompt", new_column_name="topic")