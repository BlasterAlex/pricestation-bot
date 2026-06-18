"""add preferred_currency to users

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_currency", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "preferred_currency")
