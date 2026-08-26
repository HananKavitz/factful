"""add users.temperature and users.top_p

Revision ID: 0003_add_users_sampling_params
Revises: 0002_add_users_style_profile
Create Date: 2026-08-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_add_users_sampling_params"
down_revision = "0002_add_users_style_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("top_p", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "top_p")
    op.drop_column("users", "temperature")
