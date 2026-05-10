"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), unique=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ps_id", sa.String(64), unique=True, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("cover_url", sa.Text(), nullable=True),
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
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False
        ),
        sa.Column(
            "region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False
        ),
        sa.Column("target_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
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

    op.create_table(
        "user_regions",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "region_id", sa.Integer(), sa.ForeignKey("regions.id"), primary_key=True
        ),
    )



def downgrade() -> None:
    op.drop_table("user_regions")
    op.drop_table("notifications")
    op.drop_table("subscriptions")
    op.drop_table("prices")
    op.drop_table("games")
    op.drop_table("regions")
    op.drop_table("users")
