from unittest.mock import AsyncMock

import pytest

from services.notifier import notify_price_drop
from services.ps_store import GameInfo

COVER = "https://example.com/cover.jpg"


def _game(cover_url: str | None) -> GameInfo:
    return GameInfo(title="Test", platforms=["PS5"], type="FULL_GAME", cover_url=cover_url)


@pytest.mark.asyncio
async def test_price_drop_sends_photo_when_caption_fits(mocker):
    mocker.patch("services.notifier.format_game_card", return_value="card")
    bot = AsyncMock()

    await notify_price_drop(bot, 11, 7, _game(COVER), {}, None, {})

    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.args[0] == 11
    assert bot.send_photo.await_args.args[1] == COVER
    assert bot.send_photo.await_args.kwargs["caption"] == "card"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_drop_sends_photo_when_only_markup_is_long(mocker):
    text = '<a href="' + ("u" * 5000) + '">ok</a>'
    mocker.patch("services.notifier.format_game_card", return_value=text)
    bot = AsyncMock()

    await notify_price_drop(bot, 11, 7, _game(COVER), {}, None, {})

    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.kwargs["caption"] == text
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_drop_sends_text_when_caption_exceeds_limit(mocker):
    mocker.patch("services.notifier.format_game_card", return_value="🔔" * 513)
    bot = AsyncMock()

    await notify_price_drop(bot, 11, 7, _game(COVER), {}, None, {})

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 11
    assert bot.send_message.await_args.args[1] == "🔔" * 513
    bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_drop_sends_text_when_no_cover(mocker):
    mocker.patch("services.notifier.format_game_card", return_value="card")
    bot = AsyncMock()

    await notify_price_drop(bot, 11, 7, _game(None), {}, None, {})

    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
