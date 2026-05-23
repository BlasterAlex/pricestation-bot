"""rename normalized_title to composite_key and switch to composite format

normalized_title is renamed to composite_key. The value changes from a
plain normalized title string to a composite key that encodes edition and
platform: "{norm_title}_{type}_{platform1}_{platform2}".

Examples:
  "bloodborne_full_game_ps4"
  "minecraft_full_game_ps5"
  "minecraft_premium_edition_ps4_ps5"

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_PUNCT = re.compile(r"[™®©:().,'\"!?\-/]")
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_SPACES = re.compile(r"\s+")


def _normalize(title: str) -> str:
    t = _PUNCT.sub("", title.lower())
    t = _NON_ASCII.sub("", t)
    return _SPACES.sub("", t)


def _composite_key(title: str, game_type: str | None, platforms: list[str] | None) -> str:
    norm = _normalize(title)
    type_part = (game_type or "").lower()
    plat_part = "_".join(sorted(p.lower() for p in (platforms or [])))
    return f"{norm}_{type_part}_{plat_part}"


def upgrade() -> None:
    conn = op.get_bind()

    op.drop_index("uq_games_normalized_title", table_name="games")
    op.alter_column("games", "normalized_title", new_column_name="composite_key",
                    type_=sa.String(512), nullable=False)
    op.create_index("uq_games_composite_key", "games", ["composite_key"], unique=True)

    rows = conn.execute(
        sa.text("SELECT id, title, game_type, platforms FROM games")
    ).fetchall()
    for row in rows:
        new_key = _composite_key(row.title, row.game_type, row.platforms)
        conn.execute(
            sa.text("UPDATE games SET composite_key = :key WHERE id = :id"),
            {"key": new_key, "id": row.id},
        )


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_index("uq_games_composite_key", table_name="games")
    op.alter_column("games", "composite_key", new_column_name="normalized_title",
                    type_=sa.String(256), nullable=False)
    op.create_index("uq_games_normalized_title", "games", ["normalized_title"], unique=True)

    # Restore to plain normalized title (strip the _type_platforms suffix)
    rows = conn.execute(sa.text("SELECT id, composite_key FROM games")).fetchall()
    for row in rows:
        original = row.composite_key.split("_")[0]
        conn.execute(
            sa.text("UPDATE games SET normalized_title = :key WHERE id = :id"),
            {"key": original, "id": row.id},
        )
