import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GameRegion, Subscription, UserRegion
from services.price import get_game_regions_to_check

PS_ID = "EP0001-CUSA00001_00-TESTGAME"


@pytest_asyncio.fixture
async def game_region(session: AsyncSession, game, region):
    gr = GameRegion(game_id=game.id, region_id=region.id, ps_id=PS_ID, current_price=49.99)
    session.add(gr)
    await session.flush()
    return gr


@pytest_asyncio.fixture
async def subscription(session: AsyncSession, user, game):
    sub = Subscription(user_id=user.id, game_id=game.id)
    session.add(sub)
    await session.flush()
    return sub


@pytest_asyncio.fixture
async def user_region(session: AsyncSession, user, region):
    ur = UserRegion(user_id=user.id, region_id=region.id)
    session.add(ur)
    await session.flush()
    return ur


@pytest.mark.asyncio
async def test_get_game_regions_to_check_returns_subscribed(session, game_region, subscription, user_region):
    rows = await get_game_regions_to_check(session)
    assert any(gr.id == game_region.id for gr in rows)


@pytest.mark.asyncio
async def test_get_game_regions_to_check_excludes_without_ps_id(session, game, region, subscription, user_region):
    gr = GameRegion(game_id=game.id, region_id=region.id, ps_id=None, current_price=49.99)
    session.add(gr)
    await session.flush()

    rows = await get_game_regions_to_check(session)
    assert all(r.ps_id is not None for r in rows)


@pytest.mark.asyncio
async def test_get_game_regions_to_check_excludes_without_subscriber(session, game_region):
    rows = await get_game_regions_to_check(session)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_get_game_regions_to_check_excludes_without_user_region(session, game_region, subscription):
    rows = await get_game_regions_to_check(session)
    assert len(rows) == 0
