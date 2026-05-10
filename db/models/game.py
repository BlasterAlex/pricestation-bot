from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    ps_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="game")
    prices: Mapped[list["Price"]] = relationship(back_populates="game")
