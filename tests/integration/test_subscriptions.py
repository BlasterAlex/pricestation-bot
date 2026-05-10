import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Price, Subscription
from services.price import get_active_pairs, get_latest_price


@pytest.fixture
async def subscription(session: AsyncSession, user, game, region):
    sub = Subscription(user_id=user.id, game_id=game.id, region_id=region.id)
    session.add(sub)
    await session.flush()
    return sub


@pytest.mark.asyncio
async def test_get_active_pairs(session: AsyncSession, subscription):
    pairs = await get_active_pairs(session)
    assert (subscription.game_id, subscription.region_id) in pairs


@pytest.mark.asyncio
async def test_get_latest_price_empty(session: AsyncSession, game, region):
    result = await get_latest_price(session, game.id, region.id)
    assert result is None


@pytest.mark.asyncio
async def test_get_latest_price(session: AsyncSession, game, region):
    session.add(Price(game_id=game.id, region_id=region.id, amount=999.0))
    await session.commit()

    result = await get_latest_price(session, game.id, region.id)
    assert result is not None
    assert float(result.amount) == 999.0
