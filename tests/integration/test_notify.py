from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GameRegion, PriceDrop, Subscription
from db.models.user import User
from db.models.user_region import UserRegion
from worker.tasks.notify import send_notifications

PS_ID = "EP0001-CUSA00001_00-TESTGAME"
COVER_URL = "https://example.com/cover.jpg"


def _factory(session):
    @asynccontextmanager
    async def _ctx():
        yield session
    return lambda: _ctx()


@pytest_asyncio.fixture
async def region_usd(session: AsyncSession, region):
    region.currency = "$"
    await session.flush()
    return region


@pytest_asyncio.fixture
async def user_with_region(session: AsyncSession, user, region_usd):
    session.add(UserRegion(user_id=user.id, region_id=region_usd.id))
    await session.flush()
    return user


@pytest_asyncio.fixture
async def game_region(session: AsyncSession, game, region_usd):
    gr = GameRegion(
        game_id=game.id,
        region_id=region_usd.id,
        ps_id=PS_ID,
        current_price=29.99,
        old_price=49.99,
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


@pytest_asyncio.fixture
async def price_drop(session: AsyncSession, game):
    drop = PriceDrop(
        game_id=game.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=9),
    )
    session.add(drop)
    await session.flush()
    return drop


# ── notified_at ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notified_at_set_after_send(
    session, game_region, subscription, user_with_region, price_drop, mocker
):
    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))

    await send_notifications(AsyncMock())

    assert price_drop.notified_at is not None


@pytest.mark.asyncio
async def test_no_pending_drops_nothing_sent(session, mocker):
    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))
    bot = AsyncMock()

    await send_notifications(bot)

    bot.send_photo.assert_not_called()
    bot.send_message.assert_not_called()


# ── send_photo / send_message ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_photo_called_when_cover_url(
    session, game, game_region, subscription, user_with_region, price_drop, mocker
):
    game.cover_url = COVER_URL
    await session.flush()

    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))
    bot = AsyncMock()

    await send_notifications(bot)

    bot.send_photo.assert_called_once()
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_called_when_no_cover(
    session, game_region, subscription, user_with_region, price_drop, mocker
):
    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))
    bot = AsyncMock()

    await send_notifications(bot)

    bot.send_message.assert_called_once()
    bot.send_photo.assert_not_called()


# ── region filtering ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_notification_when_user_has_no_matching_region(
    session, game_region, user, game, price_drop, mocker
):
    # user has no regions — subscription exists but no tracked region matches game_region
    session.add(Subscription(user_id=user.id, game_id=game.id))
    await session.flush()

    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))
    bot = AsyncMock()

    await send_notifications(bot)

    bot.send_photo.assert_not_called()
    bot.send_message.assert_not_called()


# ── exception handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_continues_after_failed_send(
    session: AsyncSession, game, game_region, region_usd, mocker
):
    """If notify fails for one user, the next user is still notified and the drop is marked."""
    user1 = User(telegram_id=111, username="user1")
    user2 = User(telegram_id=222, username="user2")
    session.add_all([user1, user2])
    await session.flush()

    for u in (user1, user2):
        session.add(UserRegion(user_id=u.id, region_id=region_usd.id))
        session.add(Subscription(user_id=u.id, game_id=game.id))

    drop = PriceDrop(
        game_id=game.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=9),
    )
    session.add(drop)
    await session.flush()

    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))

    calls = []

    async def _notify(*_, **kwargs):
        calls.append(kwargs["telegram_id"])
        if kwargs["telegram_id"] == 111:
            raise RuntimeError("Telegram API error")

    mocker.patch("worker.tasks.notify.notify_price_drop", side_effect=_notify)

    await send_notifications(AsyncMock())

    assert set(calls) == {111, 222}
    assert drop.notified_at is not None


# ── current_price = None ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_notification_when_game_region_has_no_price(
    session: AsyncSession, game, region_usd, user, mocker
):
    """GameRegion with current_price=None must not trigger a notification."""
    gr = GameRegion(
        game_id=game.id,
        region_id=region_usd.id,
        ps_id=PS_ID,
        current_price=None,
    )
    session.add(gr)
    session.add(UserRegion(user_id=user.id, region_id=region_usd.id))
    session.add(Subscription(user_id=user.id, game_id=game.id))
    drop = PriceDrop(
        game_id=game.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=9),
    )
    session.add(drop)
    await session.flush()

    mocker.patch("worker.tasks.notify.AsyncSessionFactory", _factory(session))
    mocker.patch("worker.tasks.notify.get_rates", AsyncMock(return_value={}))
    bot = AsyncMock()

    await send_notifications(bot)

    bot.send_photo.assert_not_called()
    bot.send_message.assert_not_called()
