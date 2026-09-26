from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.regions import on_cancel, on_region_search, on_settings_regions_add
from bot.keyboards.inline import cancel_keyboard
from bot.states.subscription import RegionForm


def _make_message(text: str) -> AsyncMock:
    msg = AsyncMock()
    msg.text = text
    msg.from_user = MagicMock(id=1, username="user")
    return msg


def _make_callback() -> AsyncMock:
    cb = AsyncMock()
    cb.message = AsyncMock()
    return cb


@pytest.fixture
def region_search_mocks(mocker):
    mocker.patch("bot.handlers.regions.get_or_create_user", new_callable=AsyncMock)
    mocker.patch("bot.handlers.regions.get_user_regions", new_callable=AsyncMock, return_value=[])
    mocker.patch(
        "bot.handlers.regions.get_ps_regions",
        new_callable=AsyncMock,
        return_value=[{"name": "United States", "locale": "en-us"}],
    )
    mocker.patch("bot.handlers.regions.ps_regions_keyboard", return_value=MagicMock())


@pytest.mark.asyncio
async def test_on_region_search_no_results_prompts_retry_with_cancel(region_search_mocks):
    """Empty results keep waiting_for_search and offer Cancel."""
    msg = _make_message("zzzznonexistent")

    await on_region_search(msg, AsyncMock())

    msg.answer.assert_called_once()
    text, kwargs = msg.answer.call_args.args[0], msg.answer.call_args.kwargs
    assert "no results" in text.lower()
    assert kwargs["reply_markup"].inline_keyboard == cancel_keyboard().inline_keyboard


@pytest.mark.asyncio
async def test_on_region_search_with_results_shows_matches(region_search_mocks):
    msg = _make_message("united")

    await on_region_search(msg, AsyncMock())

    msg.answer.assert_called_once()
    assert "found" in msg.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_retry_search_after_no_results_then_cancel(region_search_mocks):
    """No results → new query still works → Cancel clears FSM."""
    session = AsyncMock()

    miss = _make_message("zzzznonexistent")
    await on_region_search(miss, session)
    assert "no results" in miss.answer.call_args.args[0].lower()

    hit = _make_message("united")
    await on_region_search(hit, session)
    assert "found" in hit.answer.call_args.args[0].lower()

    state = AsyncMock()
    cb = _make_callback()
    await on_cancel(cb, state)

    state.clear.assert_called_once()
    cb.message.edit_text.assert_called_once()
    assert "cancel" in cb.message.edit_text.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_on_settings_regions_add_sets_waiting_for_search():
    state = AsyncMock()
    cb = _make_callback()

    await on_settings_regions_add(cb, state)

    state.set_state.assert_called_once_with(RegionForm.waiting_for_search)
    cb.message.edit_text.assert_called_once()
    cb.answer.assert_called_once()
