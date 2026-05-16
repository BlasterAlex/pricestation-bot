"""add created_at to games, game_regions, regions, user_regions

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column("game_regions", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column("regions", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column("user_regions", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("user_regions", "created_at")
    op.drop_column("regions", "created_at")
    op.drop_column("game_regions", "created_at")
    op.drop_column("games", "created_at")
