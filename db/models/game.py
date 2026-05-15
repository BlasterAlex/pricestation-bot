
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (Index("uq_games_normalized_title", "normalized_title", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(256), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    game_type: Mapped[str | None] = mapped_column(String(64))
    platforms: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="game")
    game_regions: Mapped[list["GameRegion"]] = relationship(back_populates="game")
