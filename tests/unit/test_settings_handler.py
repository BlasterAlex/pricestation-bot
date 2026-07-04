from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.settings import (
    POPULAR_CURRENCIES,
    _currency_label,
    cmd_settings,
    on_currency_select,
    on_settings_currency_set,
)
from bot.keyboards.inline import (
    currency_suggestions_keyboard,
    settings_currency_keyboard,
    settings_main_keyboard,
)


def test_currency_label_with_distinct_symbol():
    assert _currency_label("USD") == "USD ($)"


def test_currency_label_with_distinct_symbol_euro():
    assert _currency_label("EUR") == "EUR (€)"


def test_currency_label_same_as_code():
    assert _currency_label("RUB") == "RUB"


def test_settings_main_keyboard():
    kb = settings_main_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert callbacks == ["settings:currency", "settings:history", "settings:regions"]


def test_settings_history_keyboard_selected_is_noop():
    from bot.keyboards.inline import settings_history_keyboard

    kb = settings_history_keyboard("duration")
    choice_buttons = [
        btn for row in kb.inline_keyboard for btn in row
        if btn.callback_data in ("noop", "settings:history:duration", "settings:history:date")
    ]
    by_text = {btn.text: btn.callback_data for btn in choice_buttons}
    assert by_text["✓ Duration"] == "noop"
    assert by_text["Date"] == "settings:history:date"


def test_settings_history_keyboard_date_selected():
    from bot.keyboards.inline import settings_history_keyboard

    kb = settings_history_keyboard("date")
    choice_buttons = [
        btn for row in kb.inline_keyboard for btn in row
        if btn.callback_data in ("noop", "settings:history:duration", "settings:history:date")
    ]
    by_text = {btn.text: btn.callback_data for btn in choice_buttons}
    assert by_text["Duration"] == "settings:history:duration"
    assert by_text["✓ Date"] == "noop"


def test_settings_currency_keyboard():
    kb = settings_currency_keyboard({"EUR": 0.92, "TRY": 34.0}, POPULAR_CURRENCIES)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "settings:currency:USD" in callbacks
    assert "settings:currency:EUR" in callbacks
    assert "settings:currency:custom" in callbacks
    assert "settings:show" in callbacks


def test_currency_suggestions_keyboard_callback_data():
    suggestions = [("EUR", "Euro"), ("GBP", "Pound Sterling")]
    kb = currency_suggestions_keyboard(suggestions)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "currency_select:EUR" in callbacks


def _make_message(text: str = "/settings", user_id: int = 1) -> AsyncMock:
    msg = AsyncMock()
    msg.text = text
    msg.from_user = MagicMock(id=user_id, username="user")
    return msg


def _make_user(preferred_currency: str | None = None) -> MagicMock:
    user = MagicMock()
    user.preferred_currency = preferred_currency
    user.history_display_format = None
    return user


@pytest.fixture
def common_mocks(mocker):
    mocker.patch("bot.handlers.settings.get_user_regions", new_callable=AsyncMock, return_value=[])
    mocker.patch("bot.handlers.settings.get_rates", new_callable=AsyncMock, return_value={"EUR": 0.92})


@pytest.mark.asyncio
async def test_format_tracked_regions_empty():
    from bot.handlers.settings import _format_tracked_regions

    assert "none" in _format_tracked_regions([])


def test_format_tracked_regions_bullet_list():
    from types import SimpleNamespace

    from bot.handlers.settings import _format_tracked_regions

    regions = [
        SimpleNamespace(code="tr-tr", name="Turkey"),
        SimpleNamespace(code="en-us", name="United States"),
    ]
    text = _format_tracked_regions(regions)
    assert "•" in text
    assert "Turkey" in text
    assert "United States" in text
    assert text.count("\n") == 1


@pytest.mark.asyncio
async def test_cmd_settings_shows_current_default(mocker, common_mocks):
    user = _make_user(preferred_currency=None)
    mocker.patch("bot.handlers.settings.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/settings")

    await cmd_settings(msg, AsyncMock())

    msg.answer.assert_called_once()
    text = msg.answer.call_args.args[0]
    assert "USD" in text
    assert msg.answer.call_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_on_settings_currency_set(mocker, common_mocks):
    user = _make_user()
    mocker.patch("bot.handlers.settings.get_or_create_user", new_callable=AsyncMock, return_value=user)
    session = AsyncMock()
    cb = AsyncMock()
    cb.data = "settings:currency:EUR"
    cb.from_user = MagicMock(id=1, username="user")
    cb.message = AsyncMock()

    await on_settings_currency_set(cb, session)

    assert user.preferred_currency == "EUR"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_on_currency_select_sets_currency(mocker, common_mocks):
    user = _make_user()
    mocker.patch("bot.handlers.settings.get_or_create_user", new_callable=AsyncMock, return_value=user)
    session = AsyncMock()
    cb = AsyncMock()
    cb.data = "currency_select:GBP"
    cb.from_user = MagicMock(id=1, username="user")
    cb.message = AsyncMock()

    await on_currency_select(cb, AsyncMock(), session)

    assert user.preferred_currency == "GBP"
    session.commit.assert_called_once()
