"""add price_history and history_display_format

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_price_history_game_region_recorded",
        "price_history",
        ["game_id", "region_id", sa.text("recorded_at DESC")],
    )
    op.add_column("users", sa.Column("history_display_format", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "history_display_format")
    op.drop_index("ix_price_history_game_region_recorded", table_name="price_history")
    op.drop_table("price_history")
