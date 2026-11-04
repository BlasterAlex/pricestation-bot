from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.subscriptions import on_subs_detail

COVER = "https://example.com/cover.jpg"


def _callback(data: str = "subs_detail:7") -> AsyncMock:
    cb = AsyncMock()
    cb.data = data
    cb.from_user = MagicMock(id=1, username="tester")
    cb.message = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_on_subs_detail_sends_cover_from_loaded_card(mocker):
    keyboard = MagicMock()
    mocker.patch(
        "bot.handlers.subscriptions._load_subscribed_game_card",
        new_callable=AsyncMock,
        return_value=("card", keyboard, COVER),
    )
    cb = _callback()

    await on_subs_detail(cb, AsyncMock())

    cb.message.answer_photo.assert_awaited_once_with(
        photo=COVER,
        caption="card",
        reply_markup=keyboard,
    )
    cb.message.answer.assert_not_awaited()
