"""add users.style_profile

Revision ID: 0002_add_users_style_profile
Revises: 0001_baseline
Create Date: 2026-08-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_add_users_style_profile"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("style_profile", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "style_profile")
