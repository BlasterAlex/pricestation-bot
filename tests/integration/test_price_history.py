from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_past_sales_lines
from db.models import Game, GameRegion, PriceHistory, Subscription, UserRegion
from services.price_history import UserGameSaleHistory, get_user_game_sale_history
from services.ps_store import GameInfo, RegionPrice
from services.subscription import subscribe_to_game
from worker.tasks.price_check import _check_game_region


@pytest_asyncio.fixture
async def user_region(session: AsyncSession, user, region):
    ur = UserRegion(user_id=user.id, region_id=region.id)
    session.add(ur)
    await session.flush()
    return ur


@pytest_asyncio.fixture
async def game_region(session: AsyncSession, game, region):
    gr = GameRegion(
        game_id=game.id,
        region_id=region.id,
        ps_id="EP0001-CUSA00001_00-TESTGAME",
        current_price=49.99,
    )
    session.add(gr)
    await session.flush()
    return gr


@pytest_asyncio.fixture
async def subscription(session: AsyncSession, user, game):
    sub = Subscription(user_id=user.id, game_id=game.id)
    session.add(sub)
    await session.flush()
    return sub


@pytest.mark.asyncio
async def test_price_drop_creates_history_record(session, game_region, subscription, mocker):
    from services.ps_store import GameInfo, RegionPrice

    mocker.patch(
        "worker.tasks.price_check.get_game_info",
        return_value=(GameInfo(title="Test", platforms=["PS5"], type="FULL_GAME", cover_url=None),
                      RegionPrice(price=29.99, currency="$", base_price=49.99, discount_text="-40%")),
    )
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceHistory))).scalars().all()
    assert len(rows) == 1
    assert float(rows[0].price) == 29.99


@pytest.mark.asyncio
async def test_no_history_when_price_unchanged(session, game_region, subscription, mocker):
    from services.ps_store import GameInfo, RegionPrice

    mocker.patch(
        "worker.tasks.price_check.get_game_info",
        return_value=(GameInfo(title="Test", platforms=["PS5"], type="FULL_GAME", cover_url=None),
                      RegionPrice(price=49.99, currency="$", base_price=None, discount_text=None)),
    )
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceHistory))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_history_filtered_by_subscription_date(
    session, user, game, region, user_region, game_region, subscription,
):
    region.currency = "TL"
    subscription.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await session.flush()

    old_sale = PriceHistory(
        game_id=game.id,
        region_id=region.id,
        price=10.0,
        recorded_at=datetime.now(timezone.utc) - timedelta(days=100),
    )
    new_sale = PriceHistory(
        game_id=game.id,
        region_id=region.id,
        price=20.0,
        recorded_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    session.add_all([old_sale, new_sale])
    await session.flush()

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=10)
    assert history is not None
    assert history.total_sales == 1
    assert history.regions[0].sales[0][0] == 20.0


@pytest.mark.asyncio
async def test_history_has_more_when_over_limit(
    session, user, game, region, user_region, game_region, subscription,
):
    subscription.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await session.flush()

    for i in range(5):
        session.add(PriceHistory(
            game_id=game.id,
            region_id=region.id,
            price=10.0 + i,
            recorded_at=datetime.now(timezone.utc) - timedelta(days=i + 1),
        ))
    await session.flush()

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=3)
    assert history is not None
    assert history.has_more is True
    assert len(history.regions[0].sales) == 3


def test_format_past_sales_shows_tracking_when_no_sales():
    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        regions=[],
        total_sales=0,
    )
    lines = format_past_sales_lines(history, "duration", limit_per_region=3)
    assert lines == ["\n<i>Tracking since 01 Jan 2026</i>"]
    assert "Past sales" not in "".join(lines)


@pytest.mark.asyncio
async def test_active_promo_hidden_until_discount_end(
    session, user, game, region, user_region, game_region, subscription,
):
    end = datetime.now(timezone.utc) + timedelta(days=7)
    subscription.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    await session.flush()
    session.add(PriceHistory(
        game_id=game.id,
        region_id=region.id,
        price=29.99,
        discount_end=end,
    ))
    await session.flush()

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=10)
    assert history is not None
    assert history.total_sales == 0
    assert history.regions == []


@pytest.mark.asyncio
async def test_ended_promo_visible_with_discount_end_date(
    session, user, game, region, user_region, game_region, subscription,
):
    end = datetime.now(timezone.utc) - timedelta(days=2)
    subscription.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await session.flush()
    session.add(PriceHistory(
        game_id=game.id,
        region_id=region.id,
        price=29.99,
        recorded_at=datetime.now(timezone.utc) - timedelta(days=10),
        discount_end=end,
    ))
    await session.flush()

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=10)
    assert history is not None
    assert history.total_sales == 1
    assert history.regions[0].sales[0][0] == 29.99
    assert history.regions[0].sales[0][1] == end


@pytest.mark.asyncio
async def test_permanent_drop_visible_immediately(
    session, user, game, region, user_region, game_region, subscription,
):
    recorded = datetime.now(timezone.utc) - timedelta(hours=1)
    subscription.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    await session.flush()
    session.add(PriceHistory(
        game_id=game.id,
        region_id=region.id,
        price=39.99,
        recorded_at=recorded,
    ))
    await session.flush()

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=10)
    assert history is not None
    assert history.total_sales == 1
    assert history.regions[0].sales[0][1] == recorded


@pytest.mark.asyncio
async def test_subscribe_seeds_promo_hidden_until_end(
    session, user, region, user_region,
):
    end = datetime.now(timezone.utc) + timedelta(days=7)
    game_info = GameInfo(title="Test Game", platforms=["PS5"], type="FULL_GAME", cover_url=None)
    prices = {
        region.code: RegionPrice(
            ps_id="EP0001-PPSA00001_00-TESTGAME",
            price=29.99,
            currency="$",
            base_price=59.99,
            discount_text="-50%",
            discount_end=end,
        ),
    }
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    db_rows = (await session.scalars(select(PriceHistory).where(PriceHistory.game_id == game.id))).all()
    assert len(db_rows) == 1
    assert db_rows[0].discount_end == end

    history = await get_user_game_sale_history(session, user.id, game.id, limit_per_region=10)
    assert history is not None
    assert history.total_sales == 0
    assert history.regions == []


@pytest.mark.asyncio
async def test_price_drop_stores_discount_end(session, game_region, subscription, mocker):
    from services.ps_store import GameInfo

    end = datetime(2026, 7, 16, 6, 59, tzinfo=timezone.utc)
    mocker.patch(
        "worker.tasks.price_check.get_game_info",
        return_value=(
            GameInfo(title="Test", platforms=["PS5"], type="FULL_GAME", cover_url=None),
            RegionPrice(price=29.99, currency="$", base_price=49.99, discount_text="-40%", discount_end=end),
        ),
    )
    await _check_game_region(session, game_region)

    row = await session.scalar(select(PriceHistory).where(PriceHistory.game_id == game_region.game_id))
    assert row is not None
    assert row.discount_end == end


@pytest.mark.asyncio
async def test_record_active_sales_skips_full_price(session, game, region):
    from services.price_history import record_active_sales_on_subscribe

    prices = {
        region.code: RegionPrice(
            ps_id="x", price=59.99, currency="$", base_price=None, discount_text=None,
        ),
    }
    await record_active_sales_on_subscribe(session, game.id, prices, {region.code: region})
    await session.flush()

    count = await session.scalar(select(PriceHistory).where(PriceHistory.game_id == game.id))
    assert count is None


@pytest.mark.asyncio
async def test_record_active_sales_stores_discount_end(session, game, region):
    from services.price_history import record_active_sales_on_subscribe

    end = datetime(2026, 7, 16, 6, 59, tzinfo=timezone.utc)
    prices = {
        region.code: RegionPrice(
            ps_id="x", price=29.99, currency="$", base_price=59.99,
            discount_text="-50%", discount_end=end,
        ),
    }
    await record_active_sales_on_subscribe(session, game.id, prices, {region.code: region})
    await session.flush()

    row = await session.scalar(select(PriceHistory).where(PriceHistory.game_id == game.id))
    assert row is not None
    assert float(row.price) == 29.99
    assert row.discount_end == end
