from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.currency import _currency_label, cmd_currency, on_currency_select
from bot.keyboards.inline import currency_suggestions_keyboard

# ── _currency_label ───────────────────────────────────────────────────────────


def test_currency_label_with_distinct_symbol():
    assert _currency_label("USD") == "USD ($)"


def test_currency_label_with_distinct_symbol_euro():
    assert _currency_label("EUR") == "EUR (€)"


def test_currency_label_same_as_code():
    # RUB has no PS symbol → falls back to code itself
    assert _currency_label("RUB") == "RUB"


def test_currency_label_unknown_code():
    assert _currency_label("XYZ") == "XYZ"


# ── currency_suggestions_keyboard ─────────────────────────────────────────────


def test_currency_suggestions_keyboard_callback_data():
    suggestions = [("EUR", "Euro"), ("GBP", "Pound Sterling")]
    kb = currency_suggestions_keyboard(suggestions)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "currency_select:EUR" in callbacks
    assert "currency_select:GBP" in callbacks


def test_currency_suggestions_keyboard_button_text():
    suggestions = [("EUR", "Euro")]
    kb = currency_suggestions_keyboard(suggestions)
    assert kb.inline_keyboard[0][0].text == "EUR — Euro"


def test_currency_suggestions_keyboard_one_per_row():
    suggestions = [("USD", "US Dollar"), ("EUR", "Euro"), ("GBP", "Pound Sterling")]
    kb = currency_suggestions_keyboard(suggestions)
    assert all(len(row) == 1 for row in kb.inline_keyboard)


def test_currency_suggestions_keyboard_count():
    suggestions = [("USD", "US Dollar"), ("EUR", "Euro")]
    kb = currency_suggestions_keyboard(suggestions)
    assert len(kb.inline_keyboard) == 2


# ── cmd_currency handler ──────────────────────────────────────────────────────


def _make_message(text: str = "/currency", user_id: int = 1) -> AsyncMock:
    msg = AsyncMock()
    msg.text = text
    msg.from_user = MagicMock(id=user_id, username="user")
    return msg


def _make_user(preferred_currency: str | None = None) -> MagicMock:
    user = MagicMock()
    user.preferred_currency = preferred_currency
    return user


@pytest.fixture
def common_mocks(mocker):
    mocker.patch("bot.handlers.currency.get_rates", new_callable=AsyncMock, return_value={"EUR": 0.92, "GBP": 0.79})


@pytest.mark.asyncio
async def test_cmd_currency_no_arg_shows_current_default(mocker, common_mocks):
    user = _make_user(preferred_currency=None)
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/currency")

    await cmd_currency(msg, AsyncMock())

    msg.answer.assert_called_once()
    text = msg.answer.call_args.args[0]
    assert "USD" in text


@pytest.mark.asyncio
async def test_cmd_currency_no_arg_shows_preferred(mocker, common_mocks):
    user = _make_user(preferred_currency="EUR")
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/currency")

    await cmd_currency(msg, AsyncMock())

    text = msg.answer.call_args.args[0]
    assert "EUR" in text


@pytest.mark.asyncio
async def test_cmd_currency_exact_match_sets_currency(mocker, common_mocks):
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    session = AsyncMock()
    msg = _make_message("/currency EUR")

    await cmd_currency(msg, session)

    assert user.preferred_currency == "EUR"
    session.commit.assert_called_once()
    msg.answer.assert_called_once()
    assert "EUR" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_currency_usd_sets_without_being_in_rates(mocker):
    # USD is not in rates dict (base currency) but must still be accepted
    mocker.patch("bot.handlers.currency.get_rates", new_callable=AsyncMock, return_value={"EUR": 0.92})
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/currency USD")

    await cmd_currency(msg, AsyncMock())

    assert user.preferred_currency == "USD"


@pytest.mark.asyncio
async def test_cmd_currency_not_found_with_suggestions_shows_keyboard(mocker):
    mocker.patch("bot.handlers.currency.get_rates", new_callable=AsyncMock, return_value={"RUB": 73.3, "RWF": 1467.0})
    mocker.patch(
        "bot.handlers.currency.find_currency_suggestions",
        return_value=[("RUB", "Russian Ruble"), ("RWF", "Rwanda Franc")],
    )
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/currency RYB")

    await cmd_currency(msg, AsyncMock())

    msg.answer.assert_called_once()
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is not None
    assert "RYB" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_currency_not_found_no_suggestions_shows_error(mocker):
    mocker.patch("bot.handlers.currency.get_rates", new_callable=AsyncMock, return_value={"EUR": 0.92})
    mocker.patch("bot.handlers.currency.find_currency_suggestions", return_value=[])
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    msg = _make_message("/currency ZZZ")

    await cmd_currency(msg, AsyncMock())

    msg.answer.assert_called_once()
    text = msg.answer.call_args.args[0]
    assert "ZZZ" in text
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is None


# ── on_currency_select callback ───────────────────────────────────────────────


def _make_callback(iso: str, user_id: int = 1) -> AsyncMock:
    cb = AsyncMock()
    cb.data = f"currency_select:{iso}"
    cb.from_user = MagicMock(id=user_id, username="user")
    cb.message = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_on_currency_select_sets_currency(mocker):
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    session = AsyncMock()
    cb = _make_callback("GBP")

    await on_currency_select(cb, session)

    assert user.preferred_currency == "GBP"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_on_currency_select_edits_message(mocker):
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    cb = _make_callback("GBP")

    await on_currency_select(cb, AsyncMock())

    cb.message.edit_text.assert_called_once()
    assert "GBP" in cb.message.edit_text.call_args.args[0]


@pytest.mark.asyncio
async def test_on_currency_select_answers_callback(mocker):
    user = _make_user()
    mocker.patch("bot.handlers.currency.get_or_create_user", new_callable=AsyncMock, return_value=user)
    cb = _make_callback("EUR")

    await on_currency_select(cb, AsyncMock())

    cb.answer.assert_called_once()
