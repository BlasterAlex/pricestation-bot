from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Game, GameRegion, PriceHistory, Region, Subscription, User
from services.ps_store import GameInfo, RegionPrice
from services.subscription import (
    _find_region_price,
    is_subscribed,
    subscribe_to_game,
    sync_subscriptions_for_new_region,
    unsubscribe_from_game,
)


def _make_game_info(title: str = "Test Game", type_: str = "FULL_GAME", ps_id_suffix: str | None = None) -> GameInfo:
    return GameInfo(title=title, platforms=["PS5"], type=type_, cover_url=None, ps_id_suffix=ps_id_suffix)


def _make_region_price(
    ps_id: str = "EP0001-PPSA00001_00-TESTGAME",
    price: float | None = 49.99,
    base_price: float | None = None,
    currency: str | None = "$",
    discount_end: datetime | None = None,
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


@pytest.mark.asyncio
async def test_subscribe_new_game_creates_game(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}

    await subscribe_to_game(session, user, game_info, prices)

    result = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    assert result is not None
    assert result.title == "Test Game"


@pytest.mark.asyncio
async def test_subscribe_new_game_creates_game_region(session: AsyncSession, user, region):
    game_info = _make_game_info()
    rp = _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME", price=39.99)
    prices = {region.code: rp}

    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
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
    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    sub = await session.scalar(
        select(Subscription).where(Subscription.game_id == game.id, Subscription.user_id == user.id)
    )
    assert sub is not None


@pytest.mark.asyncio
async def test_subscribe_records_active_sale_in_history(session: AsyncSession, user, region):
    game_info = _make_game_info()
    end = datetime(2026, 7, 16, 6, 59, tzinfo=timezone.utc)
    prices = {
        region.code: _make_region_price(price=29.99, base_price=59.99, discount_end=end),
    }

    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    rows = (
        await session.scalars(
            select(PriceHistory).where(
                PriceHistory.game_id == game.id,
                PriceHistory.region_id == region.id,
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].price == Decimal("29.99")
    assert rows[0].discount_end == end


@pytest.mark.asyncio
async def test_subscribe_no_history_when_not_on_sale(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(price=59.99, base_price=None)}

    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    count = await session.scalar(
        select(PriceHistory).where(PriceHistory.game_id == game.id)
    )
    assert count is None


@pytest.mark.asyncio
async def test_resubscribe_does_not_duplicate_active_sale_history(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(price=29.99, base_price=59.99)}

    await subscribe_to_game(session, user, game_info, prices)
    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is False
    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    rows = (
        await session.scalars(select(PriceHistory).where(PriceHistory.game_id == game.id))
    ).all()
    assert len(rows) == 1


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
    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
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

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
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

    game = await session.scalar(select(Game).where(Game.composite_key == ascii_game.composite_key))
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

    game = await session.scalar(select(Game).where(Game.composite_key == ascii_game.composite_key))
    assert game.title == "Test Game"


@pytest.mark.asyncio
async def test_subscribe_updates_title_when_new_has_trademark_symbols(session: AsyncSession, user, region):
    """Title with ™/® is effectively ASCII and should replace a non-ASCII stored title."""
    localized = _make_game_info(title="Набір Test Game")
    trademark = _make_game_info(title="Test Game™")
    prices = {region.code: _make_region_price()}

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, localized, prices)

    await subscribe_to_game(session, user, trademark, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == trademark.composite_key))
    assert game.title == "Test Game™"


@pytest.mark.asyncio
async def test_subscribe_updates_title_from_en_us_region(session: AsyncSession, user, region, region2):
    """When en-us is in the subscription's regions, non-ASCII stored title is updated to the canonical title."""
    localized = _make_game_info(title="Набір геймера")
    canonical = _make_game_info(title="Gamer Bundle")
    prices_localized = {region.code: _make_region_price(ps_id="EP0001")}
    prices_canonical = {
        region.code: _make_region_price(ps_id="EP0001"),
        region2.code: _make_region_price(ps_id="UP0001"),
    }

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, localized, prices_localized)

    await subscribe_to_game(session, user, canonical, prices_canonical)

    game = await session.scalar(select(Game).where(Game.composite_key == canonical.composite_key))
    assert game.title == "Gamer Bundle"


@pytest.mark.asyncio
async def test_subscribe_keeps_ascii_title_even_with_en_us_region(session: AsyncSession, user, region, region2):
    """ASCII stored title is not replaced when new title is non-ASCII, even if en-us is in prices."""
    ascii_game = _make_game_info(title="Test Game")
    localized = _make_game_info(title="Набір Test Game")
    prices_ascii = {region.code: _make_region_price(ps_id="EP0001")}
    prices_localized = {
        region.code: _make_region_price(ps_id="EP0001"),
        region2.code: _make_region_price(ps_id="UP0001"),
    }

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, ascii_game, prices_ascii)

    await subscribe_to_game(session, user, localized, prices_localized)

    game = await session.scalar(select(Game).where(Game.composite_key == ascii_game.composite_key))
    assert game.title == "Test Game"



# ── is_subscribed ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_is_subscribed_true(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}
    await subscribe_to_game(session, user, game_info, prices)

    result = await is_subscribed(session, user.telegram_id, game_info.composite_key)

    assert result is not None


@pytest.mark.asyncio
async def test_is_subscribed_false(session: AsyncSession, user):
    result = await is_subscribed(session, user.telegram_id, "nonexistentgame")

    assert result is None


# ── unsubscribe_from_game ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsubscribe_removes_subscription(session: AsyncSession, user, region):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price()}
    await subscribe_to_game(session, user, game_info, prices)

    game_id = await is_subscribed(session, user.telegram_id, game_info.composite_key)
    removed = await unsubscribe_from_game(session, user.telegram_id, game_id)

    assert removed is True
    assert await is_subscribed(session, user.telegram_id, game_info.composite_key) is None


@pytest.mark.asyncio
async def test_unsubscribe_not_subscribed_returns_false(session: AsyncSession, user):
    removed = await unsubscribe_from_game(session, user.telegram_id, 999999)

    assert removed is False


# ── sync_subscriptions_for_new_region ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_creates_game_regions_for_new_region(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

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
async def test_sync_records_active_sale_in_history(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

    mock_rp = RegionPrice(
        ps_id="UP0001-PPSA00001_00-TESTGAME", price=29.99, currency="$",
        base_price=59.99, discount_text="-50%",
        discount_end=datetime(2026, 7, 16, 6, 59, tzinfo=timezone.utc),
    )
    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=mock_rp)):
        await sync_subscriptions_for_new_region(session, user, region2)

    rows = (
        await session.scalars(
            select(PriceHistory).where(
                PriceHistory.game_id == game.id,
                PriceHistory.region_id == region2.id,
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].price == Decimal("29.99")
    assert rows[0].discount_end == mock_rp.discount_end


@pytest.mark.asyncio
async def test_sync_no_history_when_not_on_sale(session: AsyncSession, user, region, region2):
    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

    mock_rp = RegionPrice(
        ps_id="UP0001-PPSA00001_00-TESTGAME", price=59.99, currency="$",
        base_price=None, discount_text=None,
    )
    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=mock_rp)):
        await sync_subscriptions_for_new_region(session, user, region2)

    count = await session.scalar(
        select(PriceHistory).where(
            PriceHistory.game_id == game.id,
            PriceHistory.region_id == region2.id,
        )
    )
    assert count is None


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

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

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

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

    with patch("services.subscription._find_region_price", new=AsyncMock(return_value=None)):
        await sync_subscriptions_for_new_region(session, user, region2)

    gr = await session.scalar(
        select(GameRegion).where(GameRegion.game_id == game.id, GameRegion.region_id == region2.id)
    )
    assert gr is None


# ── ps_id_suffix grouping ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_stores_ps_id_suffix(session: AsyncSession, user, region):
    """subscribe_to_game saves the ps_id_suffix from GameInfo."""
    game_info = _make_game_info(ps_id_suffix="TESTGAME0000")
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME0000")}

    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    assert game.ps_id_suffix == "TESTGAME0000"


@pytest.mark.asyncio
async def test_subscribe_merges_by_suffix_different_composite_key(
    session: AsyncSession, user, region, region2
):
    """Two prices with the same suffix but different localized titles collapse into one game row."""
    en_info = _make_game_info(title="Test Game Standard Edition PS5", ps_id_suffix="TESTGAME0000")
    es_info = _make_game_info(title="Edición Estándar Test Game PS5", ps_id_suffix="TESTGAME0000")
    # Both carry the same suffix → should map to the same DB row
    en_price = _make_region_price(ps_id="UP0001-PPSA00001_00-TESTGAME0000")
    es_price = _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME0000")

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()

    # user2 subscribes via EN title
    await subscribe_to_game(session, user2, en_info, {region.code: en_price})
    # user subscribes via ES title (different composite_key, same suffix)
    await subscribe_to_game(session, user, es_info, {region2.code: es_price})

    from sqlalchemy import func as sa_func
    count = await session.scalar(select(sa_func.count()).select_from(Game))
    assert count == 1, "Suffix match should collapse to a single Game row"


@pytest.mark.asyncio
async def test_is_subscribed_true_via_suffix(session: AsyncSession, user, region, region2):
    """is_subscribed returns True when looked up by suffix even if composite_key differs."""
    en_info = _make_game_info(title="Test Game Standard Edition PS5", ps_id_suffix="TESTGAME0000")
    es_info = _make_game_info(title="Edición Estándar Test Game PS5", ps_id_suffix="TESTGAME0000")
    en_price = _make_region_price(ps_id="UP0001-PPSA00001_00-TESTGAME0000")

    await subscribe_to_game(session, user, en_info, {region.code: en_price})

    # Check subscription using the ES composite_key + suffix
    result = await is_subscribed(
        session, user.telegram_id, es_info.composite_key, suffix="TESTGAME0000"
    )
    assert result is not None


@pytest.mark.asyncio
async def test_unsubscribe_via_suffix(session: AsyncSession, user, region, region2):
    """unsubscribe_from_game removes subscription found via suffix lookup."""
    en_info = _make_game_info(title="Test Game Standard Edition PS5", ps_id_suffix="TESTGAME0000")
    es_info = _make_game_info(title="Edición Estándar Test Game PS5", ps_id_suffix="TESTGAME0000")
    en_price = _make_region_price(ps_id="UP0001-PPSA00001_00-TESTGAME0000")

    await subscribe_to_game(session, user, en_info, {region.code: en_price})

    game_id = await is_subscribed(
        session, user.telegram_id, es_info.composite_key, suffix="TESTGAME0000"
    )
    removed = await unsubscribe_from_game(session, user.telegram_id, game_id)
    assert removed is True
    assert await is_subscribed(session, user.telegram_id, en_info.composite_key) is None


@pytest.mark.asyncio
async def test_subscribe_backfills_suffix_on_existing_game(session: AsyncSession, user, region):
    """If an existing game row has no suffix, subscribe_to_game fills it in."""
    game_info_no_suffix = _make_game_info()
    # First subscribe without a suffix
    await subscribe_to_game(session, user, game_info_no_suffix, {region.code: _make_region_price(ps_id="NOPREFIX")})

    game = await session.scalar(select(Game).where(Game.composite_key == game_info_no_suffix.composite_key))
    assert game.ps_id_suffix is None

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()

    # Second subscribe carries a suffix → should be back-filled onto the existing row
    game_info_with_suffix = _make_game_info(ps_id_suffix="TESTGAME0000")
    await subscribe_to_game(
        session, user2, game_info_with_suffix,
        {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME0000")},
    )
    await session.refresh(game)
    assert game.ps_id_suffix == "TESTGAME0000"


@pytest.mark.asyncio
async def test_subscribe_already_subscribed_via_suffix_returns_false(
    session: AsyncSession, user, region, region2
):
    """Subscribing again via a different locale (same suffix, different composite_key) returns False."""
    en_info = _make_game_info(title="Test Game Standard Edition PS5", ps_id_suffix="TESTGAME0000")
    es_info = _make_game_info(title="Edición Estándar Test Game PS5", ps_id_suffix="TESTGAME0000")
    en_price = _make_region_price(ps_id="UP0001-PPSA00001_00-TESTGAME0000")
    es_price = _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME0000")

    await subscribe_to_game(session, user, en_info, {region.code: en_price})
    # Same user, same suffix, different composite_key → should be False
    created = await subscribe_to_game(session, user, es_info, {region2.code: es_price})

    assert created is False


@pytest.mark.asyncio
async def test_subscribe_backfill_does_not_overwrite_existing_suffix(
    session: AsyncSession, user, region, region2
):
    """If a game already has a suffix, subscribe_to_game must not overwrite it."""
    game_info_original = _make_game_info(ps_id_suffix="ORIGINAL0000")
    prices_first = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-ORIGINAL0000")}
    await subscribe_to_game(session, user, game_info_original, prices_first)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info_original.composite_key))
    assert game.ps_id_suffix == "ORIGINAL0000"

    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()

    # Second subscriber brings a different suffix — must not overwrite
    game_info_different = _make_game_info(ps_id_suffix="DIFFERENT0000")
    prices_second = {region2.code: _make_region_price(ps_id="UP0001-PPSA00001_00-DIFFERENT0000")}
    await subscribe_to_game(session, user2, game_info_different, prices_second)

    await session.refresh(game)
    assert game.ps_id_suffix == "ORIGINAL0000"


# ── _find_region_price ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_region_price_matches_by_suffix(mocker):
    """Matches by suffix even when composite_key differs (localized title variant)."""
    gi = GameInfo(
        title="FC 25 Edición Estándar PS5", platforms=["PS5"], type="FULL_GAME",
        cover_url=None, ps_id_suffix="25STANDARDBUNDLE",
    )
    rp = RegionPrice(
        price=59.99, currency="€", base_price=None, discount_text=None,
        ps_id="EP0006-PPSA20050_00-25STANDARDBUNDLE",
    )
    mocker.patch("services.subscription.search_games", new=AsyncMock(return_value=[(gi, rp)]))

    result = await _find_region_price(
        title="FC 25 Standard Edition PS5",
        region_code="es-mx",
        composite_key="fc25standardeditionps5_full_game_ps5",
        suffix="25STANDARDBUNDLE",
    )

    assert result is rp


@pytest.mark.asyncio
async def test_find_region_price_falls_back_to_composite_key(mocker):
    """Falls back to composite_key match when suffix is None."""
    gi = GameInfo(title="Lies of P", platforms=["PS5"], type="FULL_GAME", cover_url=None)
    rp = RegionPrice(
        price=49.99, currency="$", base_price=None, discount_text=None,
        ps_id="EP1672-PPSA00001_00-1234567890000000",
    )
    mocker.patch("services.subscription.search_games", new=AsyncMock(return_value=[(gi, rp)]))

    result = await _find_region_price(
        title="Lies of P",
        region_code="en-us",
        composite_key=gi.composite_key,
        suffix=None,
    )

    assert result is rp


@pytest.mark.asyncio
async def test_find_region_price_no_match_returns_none(mocker):
    """Returns None when neither suffix nor composite_key matches."""
    gi = GameInfo(title="Other Game", platforms=["PS5"], type="FULL_GAME", cover_url=None)
    rp = RegionPrice(price=49.99, currency="$", base_price=None, discount_text=None, ps_id="UP9999")
    mocker.patch("services.subscription.search_games", new=AsyncMock(return_value=[(gi, rp)]))

    result = await _find_region_price(
        title="Lies of P",
        region_code="en-us",
        composite_key="liesofp_full_game_ps5",
        suffix=None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_sync_passes_suffix_to_find_region_price(
    session: AsyncSession, user, region, region2
):
    """sync_subscriptions_for_new_region passes game's ps_id_suffix to _find_region_price."""
    game_info = _make_game_info(ps_id_suffix="TESTGAME0000")
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME0000")}
    await subscribe_to_game(session, user, game_info, prices)

    mock_find = AsyncMock(return_value=None)
    with patch("services.subscription._find_region_price", new=mock_find):
        await sync_subscriptions_for_new_region(session, user, region2)

    mock_find.assert_called_once()
    _, _, _, suffix = mock_find.call_args.args
    assert suffix == "TESTGAME0000"


# ── unknown region codes ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_skips_unknown_region_code_new_game(session: AsyncSession, user, region):
    """Region code in prices dict that doesn't exist in DB is silently skipped."""
    game_info = _make_game_info()
    prices = {
        region.code: _make_region_price(),
        "zz-zz": _make_region_price(ps_id="ZZ0001-PPSA00001_00-TESTGAME"),
    }

    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is True
    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    grs = (await session.scalars(select(GameRegion).where(GameRegion.game_id == game.id))).all()
    assert len(grs) == 1
    assert grs[0].region_id == region.id


@pytest.mark.asyncio
async def test_subscribe_skips_unknown_region_code_existing_game(
    session: AsyncSession, user, region
):
    """Unknown region code is silently skipped when subscribing to an existing game."""
    game_info = _make_game_info()
    user2 = User(telegram_id=999999999, username="other")
    session.add(user2)
    await session.flush()
    await subscribe_to_game(session, user2, game_info, {region.code: _make_region_price()})

    prices = {
        region.code: _make_region_price(),
        "zz-zz": _make_region_price(ps_id="ZZ0001-PPSA00001_00-TESTGAME"),
    }
    created = await subscribe_to_game(session, user, game_info, prices)

    assert created is True
    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))
    grs = (await session.scalars(select(GameRegion).where(GameRegion.game_id == game.id))).all()
    assert all(gr.region_id == region.id for gr in grs)


# ── sync: get_game_info returns None ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_get_game_info_none_skips_game_region(session: AsyncSession, user, region):
    """get_game_info returning None → no game_region created for that game."""
    eu_region = Region(code="de-de", name="Germany")
    session.add(eu_region)
    await session.flush()

    game_info = _make_game_info()
    prices = {region.code: _make_region_price(ps_id="EP0001-PPSA00001_00-TESTGAME")}
    await subscribe_to_game(session, user, game_info, prices)

    game = await session.scalar(select(Game).where(Game.composite_key == game_info.composite_key))

    with patch("services.subscription.get_game_info", new=AsyncMock(return_value=None)):
        await sync_subscriptions_for_new_region(session, user, eu_region)

    gr = await session.scalar(
        select(GameRegion).where(
            GameRegion.game_id == game.id, GameRegion.region_id == eu_region.id
        )
    )
    assert gr is None
