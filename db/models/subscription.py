from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    target_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    game: Mapped["Game"] = relationship(back_populates="subscriptions")
    region: Mapped["Region"] = relationship(back_populates="subscriptions")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="subscription")
