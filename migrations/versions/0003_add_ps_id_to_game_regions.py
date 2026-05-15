"""add ps_id to game_regions

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game_regions", sa.Column("ps_id", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("game_regions", "ps_id")
