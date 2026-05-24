from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Game, GameRegion, PriceDrop, Subscription, UserRegion
from db.models.user import User


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


async def get_pending_drops(session: AsyncSession) -> list[PriceDrop]:
    result = await session.execute(
        select(PriceDrop)
        .where(PriceDrop.notified_at.is_(None))
        .options(
            selectinload(PriceDrop.game).options(
                selectinload(Game.game_regions).selectinload(GameRegion.region),
                selectinload(Game.subscriptions)
                .selectinload(Subscription.user)
                .selectinload(User.regions),
            )
        )
    )
    return list(result.scalars().all())
