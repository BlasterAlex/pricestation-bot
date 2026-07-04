
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index(
            "ix_price_history_game_region_recorded",
            "game_id",
            "region_id",
            text("recorded_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    discount_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped["Game"] = relationship(back_populates="price_history")
    region: Mapped["Region"] = relationship()
