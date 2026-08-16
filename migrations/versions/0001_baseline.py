"""initial schema: users and stories

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("google_sub", sa.String(length=255), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("picture", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("stories")
    op.drop_table("users")
