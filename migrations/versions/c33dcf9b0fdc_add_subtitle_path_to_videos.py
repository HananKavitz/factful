"""add subtitle_path to videos

Revision ID: c33dcf9b0fdc
Revises: 0005_rename_topic_to_prompt
Create Date: 2026-09-04 18:24:25.603613

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c33dcf9b0fdc"
down_revision = "0005_rename_topic_to_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("subtitle_path", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("videos", "subtitle_path")
