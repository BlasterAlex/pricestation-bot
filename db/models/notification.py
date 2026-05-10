from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), nullable=False)
    old_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    new_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subscription: Mapped["Subscription"] = relationship(back_populates="notifications")
