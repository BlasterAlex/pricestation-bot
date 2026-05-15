from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import GameRegion, Subscription


def is_price_dropped(old_price: float, new_price: float) -> bool:
    return new_price < old_price


def price_drop_percent(old_price: float, new_price: float) -> int:
    return round((old_price - new_price) / old_price * 100)


async def get_game_regions_to_check(session: AsyncSession) -> list[GameRegion]:
    """Return GameRegion rows for games with at least one subscriber and a stored ps_id."""
    result = await session.execute(
        select(GameRegion)
        .join(Subscription, Subscription.game_id == GameRegion.game_id)
        .where(GameRegion.ps_id.isnot(None))
        .options(
            selectinload(GameRegion.game),
            selectinload(GameRegion.region),
        )
        .distinct()
    )
    return list(result.scalars().all())
