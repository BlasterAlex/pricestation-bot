"""convert created_at columns to TIMESTAMPTZ

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_TABLES = ["games", "game_regions", "regions", "subscriptions", "users", "user_regions"]


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(
            table,
            "created_at",
            type_=sa.DateTime(timezone=True),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(
            table,
            "created_at",
            type_=sa.DateTime(),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
            server_default=sa.func.now(),
        )
