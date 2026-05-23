from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import GameRegion, Subscription, UserRegion


def is_price_dropped(old_price: float, new_price: float) -> bool:
    return new_price < old_price


async def get_game_regions_to_check(session: AsyncSession) -> list[GameRegion]:
    has_subscriber_in_region = exists(
        select(Subscription.id)
        .join(UserRegion, (UserRegion.user_id == Subscription.user_id) & (UserRegion.region_id == GameRegion.region_id))
        .where(Subscription.game_id == GameRegion.game_id)
    )
    result = await session.execute(
        select(GameRegion)
        .where(GameRegion.ps_id.isnot(None))
        .where(has_subscriber_in_region)
        .options(
            selectinload(GameRegion.game),
            selectinload(GameRegion.region),
        )
    )
    return list(result.scalars().all())
