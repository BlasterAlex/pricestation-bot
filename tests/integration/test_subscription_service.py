from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Game, GameRegion, Region, Subscription, User
from services.ps_store import GameInfo, RegionPrice
from services.subscription import (
    is_subscribed,
    subscribe_to_game,
    sync_subscriptions_for_new_region,
    unsubscribe_from_game,
)


def _make_game_info(title: str = "Test Game", type_: str = "FULL_GAME") -> GameInfo:
    return GameInfo(title=title, platforms=["PS5"], type=type_, cover_url=None)


def _make_region_price(
    ps_id: str = "EP0001-PPSA00001_00-TESTGAME",
    price: float | None = 49.99,
    base_price: float | None = None,
    currency: str | None = "$",
    discount_end: str | None = None,
) -> RegionPrice:
    return RegionPrice(
        ps_id=ps_id, price=price, currency=currency,
        base_price=base_price, discount_text=None, discount_end=discount_end,
    )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def region2(session: AsyncSession):
    r = Region(code="en-us", name="United States")
    session.add(r)
    await session.flush()
    return r


# ── subscribe_to_game ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_new_game_creates_game(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}

    await subscribe_to_game(session, user, game_info, prices)

    result = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))
    assert result is not None
    assert result.title == "Test Game"


@pytest.mark.asyncio
async def test_subscribe_new_game_creates_game_region(session: AsyncSession, user, region):
    game_info = _make_game_info()
    rp = _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME", price=39.99)
    prices = {region.code: rp}

    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))
    gr = await session.scalar(select(GameRegion).where(GameRegion.game_id == game.id))
    assert gr is not None
    assert gr.ps_id == "EP0001-PPSA00001_00-TESTGAME"
    assert gr.current_price == Decimal("39.99")
    assert gr.region_id == region.id


@pytest.mark.asyncio
async def test_subscribe_new_game_creates_subscription(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}

    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is True
    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))
    sub = await session.scalar(
        select(Subscription).where(Subscription.game_id == game.id, Subscription.user_id == user.id)
    )
    assert sub is not None


@pytest.mark.asyncio
async def test_subscribe_new_game_populates_region_currency(session: AsyncSession, user, region):
    assert region.currency is None
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(currency="€")}

    await subscribe_to_game(session, user, game_info, prices)

    await session.refresh(region)
    assert region.currency == "€"


@pytest.mark.asyncio
async def test_subscribe_existing_game_not_subscribed(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, game_info, prices)

    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is True
    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))
    sub = await session.scalar(
        select(Subscription).where(Subscription.game_id == game.id, Subscription.user_id == user.id)
    )
    assert sub is not None


@pytest.mark.asyncio
async def test_subscribe_existing_game_adds_missing_game_region(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices_first = {region.code: _make_region_price(ps_id="EP0001")}

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, game_info, prices_first)

    prices_both = {
        region.code: _make_region_price(ps_id="EP0001"),
        region2.code: _make_region_price(ps_id="UP0001"),
    }
    await subscribe_to_game(session, user, game_info, prices_both)

    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))
    grs = (await session.scalars(select(GameRegion).where(GameRegion.game_id == game.id))).all()
    region_ids = {gr.region_id for gr in grs}
    assert region.id in region_ids
    assert region2.id in region_ids


@pytest.mark.asyncio
async def test_subscribe_already_subscribed_returns_false(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}

    await subscribe_to_game(session, user, game_info, prices)
    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is False


@pytest.mark.asyncio
async def test_subscribe_prefers_ascii_title(session: AsyncSession, user, region):
    localized = _make_game_info(title="Набір Test Game")
    ascii_game = _make_game_info(title="Test Game")
    prices = {region.code: _make_region_price()}

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, localized, prices)

    await subscribe_to_game(session, user, ascii_game, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == ascii_game.normalized_title))
    assert game.title == "Test Game"


@pytest.mark.asyncio
async def test_subscribe_keeps_title_if_new_is_non_ascii(session: AsyncSession, user, region):
    ascii_game = _make_game_info(title="Test Game")
    localized = _make_game_info(title="Набір Test Game")
    prices = {region.code: _make_region_price()}

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, ascii_game, prices)

    await subscribe_to_game(session, user, localized, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == ascii_game.normalized_title))
    assert game.title == "Test Game"



# ── is_subscribed ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_is_subscribed_true(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}
    await subscribe_to_game(session, user, game_info, prices)

    result = await is_subscribed(session, user.telegram_id, game_info.normalized_title)

    assert result is True


@pytest.mark.asyncio
async def test_is_subscribed_false(session: AsyncSession, user):
    result = await is_subscribed(session, user.telegram_id, "nonexistentgame")

    assert result is False


# ── unsubscribe_from_game ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsubscribe_removes_subscription(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}
    await subscribe_to_game(session, user, game_info, prices)

    removed = await unsubscribe_from_game(session, user.telegram_id, game_info.normalized_title)

    assert removed is True
    result = await is_subscribed(session, user.telegram_id, game_info.normalized_title)
    assert result is False


@pytest.mark.asyncio
async def test_unsubscribe_not_subscribed_returns_false(session: AsyncSession, user):
    removed = await unsubscribe_from_game(session, user.telegram_id, "nonexistentgame")

    assert removed is False


# ── sync_subscriptions_for_new_region ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_creates_game_regions_for_new_region(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))

    mock_rp = RegionPrice(ps_id="UP0001-PPSA00001_00-TESTGAME", price=59.99, currency="$",
                          base_price=None, discount_text=None)
    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=mock_rp)):
        await sync_subscriptions_for_new_region(session, user, region2)

    gr = await session.scalar(
        select(GameRegion).where(GameRegion.game_id == game.id, GameRegion.region_id == region2.id)
    )
    assert gr is not None
    assert gr.current_price == Decimal("59.99")


@pytest.mark.asyncio
async def test_sync_populates_region_currency(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001")}
    await subscribe_to_game(session, user, game_info, prices)

    mock_rp = RegionPrice(ps_id="UP0001", price=59.99, currency="$", base_price=None, discount_text=None)
    assert region2.currency is None
    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=mock_rp)):
        await sync_subscriptions_for_new_region(session, user, region2)

    await session.refresh(region2)
    assert region2.currency == "$"


@pytest.mark.asyncio
async def test_sync_skips_existing_game_region(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {
        region.code: _make_region_price(ps_id="EP0001"),
        region2.code: _make_region_price(ps_id="UP0001"),
    }
    await subscribe_to_game(session, user, game_info, prices)

    mock_get = AsyncMock(return_value=None)
    with patch("services.subscription.get_game_info", new=mock_get):
        await sync_subscriptions_for_new_region(session, user, region2)

    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_sync_no_subscriptions_does_nothing(session: AsyncSession, user, region2):
    mock_get = AsyncMock()
    with patch("services.subscription.get_game_info", new=mock_get):
        await sync_subscriptions_for_new_region(session, user, region2)

    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_sync_via_get_game_info_when_prefix_matches(session: AsyncSession, user, region):
    """best_ps_id finds an EP id for a new EU region → get_game_info is called, game_region created."""
    eu_region2 = Region(code="de-de", name="Germany")
    session.add(eu_region2)
    await session.flush()

    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))

    mock_rp = RegionPrice(ps_id="EP0001-PPSA00001_00-TESTGAME", price=39.99, currency="€",
                          base_price=None, discount_text=None)
    mock_get = AsyncMock(return_value=(game_info, mock_rp))
    with patch("services.subscription.get_game_info", new=mock_get):
        await sync_subscriptions_for_new_region(session, user, eu_region2)

    mock_get.assert_called_once_with("EP0001-PPSA00001_00-TESTGAME", eu_region2.code)
    gr = await session.scalar(
        select(GameRegion).where(GameRegion.game_id == game.id, GameRegion.region_id == eu_region2.id)
    )
    assert gr is not None
    assert gr.current_price == Decimal("39.99")


@pytest.mark.asyncio
async def test_sync_game_unavailable_in_new_region(session: AsyncSession, user, region, region2):
    """_find_region_price returns None (no title match in US store) → no game_region created."""
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.normalized_title == game_info.normalized_title))

    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=None)):
        await sync_subscriptions_for_new_region(session, user, region2)

    gr = await session.scalar(
        select(GameRegion).where(GameRegion.game_id == game.id, GameRegion.region_id == region2.id)
    )
    assert gr is None
