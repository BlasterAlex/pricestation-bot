from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Price, Subscription


async def get_active_pairs(session: AsyncSession) -> list[tuple[int, int]]:
    result = await session.execute(
        select(Subscription.game_id, Subscription.region_id).distinct()
    )
    return result.all()


async def get_latest_price(session: AsyncSession, game_id: int, region_id: int) -> Price | None:
    result = await session.execute(
        select(Price)
        .where(Price.game_id == game_id, Price.region_id == region_id)
        .order_by(Price.checked_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
