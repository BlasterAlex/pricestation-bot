from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Game, GameRegion, Region, Subscription, UserRegion
from services.subscription import get_user_subscriptions_page


@pytest_asyncio.fixture
async def region2(session: AsyncSession):
    r = Region(code="en-us", name="United States")
    session.add(r)
    await session.flush()
    return r


@pytest_asyncio.fixture
async def user_region(session: AsyncSession, user, region):
    ur = UserRegion(user_id=user.id, region_id=region.id)
    session.add(ur)
    await session.flush()
    return ur


async def _make_game(session: AsyncSession, title: str = "Test Game", suffix: str = "TESTGAME0000") -> Game:
    g = Game(
        title=title,
        composite_key=f"{title.lower().replace(' ', '')}_full_game_ps5",
        ps_id_suffix=suffix,
        game_type="FULL_GAME",
        platforms=["PS5"],
    )
    session.add(g)
    await session.flush()
    return g


async def _subscribe(
    session: AsyncSession, user, game, created_at: datetime | None = None
) -> Subscription:
    sub = Subscription(user_id=user.id, game_id=game.id)
    if created_at is not None:
        sub.created_at = created_at
    session.add(sub)
    await session.flush()
    return sub


async def _make_game_region(
    session: AsyncSession,
    game: Game,
    region: Region,
    price: float = 49.99,
    ps_id: str = "EP0001-TEST",
) -> GameRegion:
    gr = GameRegion(game_id=game.id, region_id=region.id, ps_id=ps_id, current_price=price)
    session.add(gr)
    await session.flush()
    return gr


# ── empty / count ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_beyond_results_returns_empty_list(session: AsyncSession, user, region, user_region):
    """total > 0 but requested page is beyond available rows → returns (total, [])."""
    game = await _make_game(session)
    await _subscribe(session, user, game)

    total, items = await get_user_subscriptions_page(session, user.telegram_id, page=1, page_size=1)

    assert total == 1
    assert items == []


@pytest.mark.asyncio
async def test_no_subscriptions_returns_empty(session: AsyncSession, user):
    total, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    assert total == 0
    assert items == []


@pytest.mark.asyncio
async def test_returns_correct_total(session: AsyncSession, user, region, user_region):
    for i in range(3):
        g = await _make_game(session, title=f"Game {i}", suffix=f"GAME{i:04d}")
        await _subscribe(session, user, g)

    total, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    assert total == 3
    assert len(items) == 3


@pytest.mark.asyncio
async def test_total_consistent_across_pages(session: AsyncSession, user, region, user_region):
    for i in range(4):
        g = await _make_game(session, title=f"Game {i}", suffix=f"GAME{i:04d}")
        await _subscribe(session, user, g)

    total0, _ = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=3)
    total1, _ = await get_user_subscriptions_page(session, user.telegram_id, page=1, page_size=3)
    assert total0 == total1 == 4


# ── sorting ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sorted_newest_first(session: AsyncSession, user, region, user_region):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for i in range(3):
        g = await _make_game(session, title=f"Game {i}", suffix=f"GAME{i:04d}")
        await _subscribe(session, user, g, created_at=base + timedelta(hours=i))

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    titles = [gi.title for gi, _ in items]
    assert titles[0] == "Game 2"
    assert titles[-1] == "Game 0"


# ── pagination ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pagination_correct_page_sizes(session: AsyncSession, user, region, user_region):
    for i in range(5):
        g = await _make_game(session, title=f"Game {i}", suffix=f"GAME{i:04d}")
        await _subscribe(session, user, g)

    total, page0 = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=3)
    _, page1 = await get_user_subscriptions_page(session, user.telegram_id, page=1, page_size=3)

    assert total == 5
    assert len(page0) == 3
    assert len(page1) == 2


@pytest.mark.asyncio
async def test_pagination_no_overlap_between_pages(session: AsyncSession, user, region, user_region):
    for i in range(5):
        g = await _make_game(session, title=f"Game {i}", suffix=f"GAME{i:04d}")
        await _subscribe(session, user, g)

    _, page0 = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=3)
    _, page1 = await get_user_subscriptions_page(session, user.telegram_id, page=1, page_size=3)

    titles0 = {gi.title for gi, _ in page0}
    titles1 = {gi.title for gi, _ in page1}
    assert titles0.isdisjoint(titles1)


# ── prices ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prices_populated_from_user_region(session: AsyncSession, user, region, user_region):
    game = await _make_game(session)
    await _make_game_region(session, game, region, price=39.99, ps_id="EP0001-TEST")
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    _, prices = items[0]
    assert region.code in prices
    rp = prices[region.code]
    assert rp.price == 39.99
    assert rp.ps_id == "EP0001-TEST"


@pytest.mark.asyncio
async def test_prices_empty_when_user_has_no_regions(session: AsyncSession, user):
    game = await _make_game(session)
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    _, prices = items[0]
    assert prices == {}


@pytest.mark.asyncio
async def test_prices_only_from_user_regions(
    session: AsyncSession, user, region, region2, user_region
):
    game = await _make_game(session)
    await _make_game_region(session, game, region, price=30.0, ps_id="TR-ID")
    await _make_game_region(session, game, region2, price=60.0, ps_id="US-ID")
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    _, prices = items[0]
    assert region.code in prices
    assert region2.code not in prices


@pytest.mark.asyncio
async def test_currency_taken_from_region(session: AsyncSession, user, region, user_region):
    region.currency = "₺"
    await session.flush()
    game = await _make_game(session)
    await _make_game_region(session, game, region, price=100.0)
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    _, prices = items[0]
    assert prices[region.code].currency == "₺"


@pytest.mark.asyncio
async def test_discount_end_formatted_as_string(session: AsyncSession, user, region, user_region):
    game = await _make_game(session)
    gr = GameRegion(
        game_id=game.id,
        region_id=region.id,
        ps_id="EP0001",
        current_price=29.99,
        discount_end=datetime(2025, 12, 31, 18, 0, tzinfo=timezone.utc),
    )
    session.add(gr)
    await session.flush()
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    _, prices = items[0]
    assert prices[region.code].discount_end == datetime(2025, 12, 31, 18, 0, tzinfo=timezone.utc)


# ── GameInfo fields ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_game_info_fields_mapped_correctly(session: AsyncSession, user, region, user_region):
    game = await _make_game(session, title="Spider-Man 2", suffix="SPIDERMAN2")
    game.cover_url = "https://example.com/cover.jpg"
    await session.flush()
    await _subscribe(session, user, game)

    _, items = await get_user_subscriptions_page(session, user.telegram_id, page=0, page_size=15)
    gi, _ = items[0]
    assert gi.title == "Spider-Man 2"
    assert gi.ps_id_suffix == "SPIDERMAN2"
    assert gi.type == "FULL_GAME"
    assert gi.cover_url == "https://example.com/cover.jpg"
    assert gi.platforms == ["PS5"]
