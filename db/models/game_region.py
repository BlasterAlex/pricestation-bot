
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class GameRegion(Base):
    __tablename__ = "game_regions"
    __table_args__ = (UniqueConstraint("game_id", "region_id", name="uq_game_regions_game_region"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    ps_id: Mapped[str | None] = mapped_column(String(128))
    current_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    old_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    base_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    discount_text: Mapped[str | None] = mapped_column(Text)
    discount_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    game: Mapped["Game"] = relationship(back_populates="game_regions")
    region: Mapped["Region"] = relationship(back_populates="game_regions")
