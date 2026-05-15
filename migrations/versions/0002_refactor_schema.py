"""refactor schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("prices")

    op.drop_column("subscriptions", "region_id")
    op.drop_column("subscriptions", "target_price")
    op.create_unique_constraint(
        "uq_subscriptions_user_game", "subscriptions", ["user_id", "game_id"]
    )
    op.create_index("ix_subscriptions_game_id", "subscriptions", ["game_id"])

    op.drop_constraint("games_ps_id_key", "games", type_="unique")
    op.alter_column("games", "ps_id", new_column_name="normalized_title")
    op.add_column("games", sa.Column("game_type", sa.String(64), nullable=True))
    op.add_column(
        "games",
        sa.Column("platforms", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.create_index(
        "uq_games_normalized_title", "games", ["normalized_title"], unique=True
    )

    op.create_table(
        "game_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False
        ),
        sa.Column(
            "region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False
        ),
        sa.Column("current_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("old_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("discount_text", sa.Text(), nullable=True),
        sa.Column("discount_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "game_id", "region_id", name="uq_game_regions_game_region"
        ),
    )


def downgrade() -> None:
    op.drop_table("game_regions")

    op.drop_index("uq_games_normalized_title", table_name="games")
    op.drop_column("games", "platforms")
    op.drop_column("games", "game_type")
    op.alter_column("games", "normalized_title", new_column_name="ps_id")
    op.create_unique_constraint("games_ps_id_key", "games", ["ps_id"])

    op.drop_index("ix_subscriptions_game_id", table_name="subscriptions")
    op.drop_constraint("uq_subscriptions_user_game", "subscriptions", type_="unique")
    op.add_column(
        "subscriptions",
        sa.Column(
            "region_id",
            sa.Integer(),
            sa.ForeignKey("regions.id"),
            nullable=False,
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("target_price", sa.Numeric(10, 2), nullable=True),
    )

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False
        ),
        sa.Column(
            "region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscriptions.id"),
            nullable=False,
        ),
        sa.Column("old_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("new_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now()),
    )
