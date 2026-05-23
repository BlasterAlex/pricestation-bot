"""add price_drops table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_drops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_price_drops_game_id", "price_drops", ["game_id"])
    op.create_index(
        "uq_price_drops_pending_game",
        "price_drops",
        ["game_id"],
        unique=True,
        postgresql_where=sa.text("notified_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_price_drops_pending_game", table_name="price_drops")
    op.drop_index("ix_price_drops_game_id", table_name="price_drops")
    op.drop_table("price_drops")
