
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class PriceDrop(Base):
    __tablename__ = "price_drops"
    __table_args__ = (
        Index("ix_price_drops_game_id", "game_id"),
        Index("uq_price_drops_pending_game", "game_id", unique=True, postgresql_where=text("notified_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped["Game"] = relationship(back_populates="price_drops")
