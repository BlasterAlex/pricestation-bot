"""add ps_id_suffix column to games

The suffix is the trailing segment of a PS Store product ID after the last "-"
(e.g. "25STANDARDBUNDLE" from "UP0006-PPSA20049_00-25STANDARDBUNDLE").
It is identical across all regional prefixes (UP/EP/HP/JP/KP) for the same
product, so it is used as the primary grouping key to merge localised-title
variants into a single card.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("ps_id_suffix", sa.String(64), nullable=True),
    )
    op.create_index("ix_games_ps_id_suffix", "games", ["ps_id_suffix"])


def downgrade() -> None:
    op.drop_index("ix_games_ps_id_suffix", table_name="games")
    op.drop_column("games", "ps_id_suffix")
