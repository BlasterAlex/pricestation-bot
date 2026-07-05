"""add show_cross_region_saves to users

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("show_cross_region_saves", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("users", "show_cross_region_saves")
