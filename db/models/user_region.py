from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class UserRegion(Base):
    __tablename__ = "user_regions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
