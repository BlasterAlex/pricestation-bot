from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GameRegion, PriceDrop, PriceHistory, Subscription
from services.ps_store import GameInfo, RegionPrice
from worker.tasks.price_check import _check_game_region, check_prices


def _factory(session):
    @asynccontextmanager
    async def _ctx():
        yield session
    return lambda: _ctx()

PS_ID = "EP0001-CUSA00001_00-TESTGAME"

_GAME_INFO = GameInfo(title="Test Game", platforms=["PS5"], type="FULL_GAME", cover_url=None)


def _region_price(price: float, base_price: float | None = None) -> RegionPrice:
    return RegionPrice(price=price, currency="$", base_price=base_price, discount_text=None)


@pytest_asyncio.fixture
async def game_region(session: AsyncSession, game, region):
    gr = GameRegion(game_id=game.id, region_id=region.id, ps_id=PS_ID, current_price=49.99)
    session.add(gr)
    await session.flush()
    return gr


@pytest_asyncio.fixture
async def game_region_no_price(session: AsyncSession, game, region):
    gr = GameRegion(game_id=game.id, region_id=region.id, ps_id=PS_ID, current_price=None)
    session.add(gr)
    await session.flush()
    return gr


@pytest_asyncio.fixture
async def subscription(session: AsyncSession, user, game):
    sub = Subscription(user_id=user.id, game_id=game.id)
    session.add(sub)
    await session.flush()
    return sub


# ── return values ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_skipped_when_api_returns_none(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=None)
    result = await _check_game_region(session, game_region)
    assert result == "skipped"


@pytest.mark.asyncio
async def test_returns_skipped_when_no_price(session, game_region, mocker):
    rp = RegionPrice(price=None, currency=None, base_price=None, discount_text=None)
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, rp))
    result = await _check_game_region(session, game_region)
    assert result == "skipped"


@pytest.mark.asyncio
async def test_returns_dropped_on_price_decrease(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    result = await _check_game_region(session, game_region)
    assert result == "dropped"


@pytest.mark.asyncio
async def test_returns_unchanged_when_price_same(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    result = await _check_game_region(session, game_region)
    assert result == "unchanged"


@pytest.mark.asyncio
async def test_returns_unchanged_when_price_increased(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(69.99)))
    result = await _check_game_region(session, game_region)
    assert result == "unchanged"


@pytest.mark.asyncio
async def test_returns_unchanged_on_first_run(session, game_region_no_price, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    result = await _check_game_region(session, game_region_no_price)
    assert result == "unchanged"


# ── price_drops table ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_price_drop_creates_record(session, game_region, subscription, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceDrop).where(PriceDrop.game_id == game_region.game_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].notified_at is None


@pytest.mark.asyncio
async def test_no_price_drop_record_when_unchanged(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceDrop).where(PriceDrop.game_id == game_region.game_id))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_price_drop_creates_history(session, game_region, subscription, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)

    rows = (
        await session.execute(
            select(PriceHistory).where(PriceHistory.game_id == game_region.game_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert float(rows[0].price) == 29.99
    assert rows[0].region_id == game_region.region_id


@pytest.mark.asyncio
async def test_no_history_when_unchanged(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceHistory))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_duplicate_drop_creates_single_record(session, game_region, subscription, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)
    await _check_game_region(session, game_region)

    rows = (await session.execute(select(PriceDrop).where(PriceDrop.game_id == game_region.game_id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_no_price_drop_on_first_run(session, game_region_no_price, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    await _check_game_region(session, game_region_no_price)

    rows = (
        (await session.execute(select(PriceDrop).where(PriceDrop.game_id == game_region_no_price.game_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 0


# ── game_region fields ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_current_price_updated(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)
    assert float(game_region.current_price) == 29.99


@pytest.mark.asyncio
async def test_old_price_set_on_drop(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)
    assert float(game_region.old_price) == 49.99


@pytest.mark.asyncio
async def test_old_price_cleared_on_increase(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(29.99)))
    await _check_game_region(session, game_region)
    assert float(game_region.old_price) == 49.99

    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(69.99)))
    await _check_game_region(session, game_region)
    assert game_region.old_price is None
    assert float(game_region.current_price) == 69.99


@pytest.mark.asyncio
async def test_last_checked_updated(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.get_game_info", return_value=(_GAME_INFO, _region_price(49.99)))
    await _check_game_region(session, game_region)
    assert game_region.last_checked is not None


# ── check_prices orchestrator ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_prices_calls_check_for_each_region(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.AsyncSessionFactory", _factory(session))
    mocker.patch(
        "worker.tasks.price_check.price.get_game_regions_to_check",
        AsyncMock(return_value=[game_region]),
    )
    mock_check = mocker.patch(
        "worker.tasks.price_check._check_game_region",
        AsyncMock(return_value="unchanged"),
    )

    await check_prices()

    mock_check.assert_called_once()
    _, called_gr = mock_check.call_args.args
    assert called_gr is game_region


@pytest.mark.asyncio
async def test_check_prices_no_regions_does_not_crash(session, mocker):
    mocker.patch("worker.tasks.price_check.AsyncSessionFactory", _factory(session))
    mocker.patch(
        "worker.tasks.price_check.price.get_game_regions_to_check",
        AsyncMock(return_value=[]),
    )
    mock_check = mocker.patch(
        "worker.tasks.price_check._check_game_region",
        AsyncMock(return_value="unchanged"),
    )

    await check_prices()

    mock_check.assert_not_called()


@pytest.mark.asyncio
async def test_check_prices_processes_multiple_regions(session, game_region, mocker):
    mocker.patch("worker.tasks.price_check.AsyncSessionFactory", _factory(session))
    mocker.patch(
        "worker.tasks.price_check.price.get_game_regions_to_check",
        AsyncMock(return_value=[game_region, game_region, game_region]),
    )
    mock_check = mocker.patch(
        "worker.tasks.price_check._check_game_region",
        AsyncMock(side_effect=["dropped", "unchanged", "skipped"]),
    )

    await check_prices()

    assert mock_check.call_count == 3
