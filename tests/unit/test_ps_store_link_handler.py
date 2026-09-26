from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.states.subscription import SearchForm
from services.ps_store import GameInfo, RegionPrice

PRODUCT_URL = (
    "https://store.playstation.com/en-us/product/"
    "UP0001-PPSA00001_00-TESTGAME00000000"
)
CONCEPT_URL = "https://store.playstation.com/en-us/concept/10016651"


def _message(text: str = PRODUCT_URL):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=123, username="tester"),
        answer=AsyncMock(),
        answer_photo=AsyncMock(),
    )


def _state():
    return SimpleNamespace(
        clear=AsyncMock(),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )


def _session():
    return SimpleNamespace(commit=AsyncMock())


@pytest.mark.asyncio
async def test_send_resolved_game_card_stores_and_sends_single_entry(mocker):
    from bot.handlers.ps_store_link import send_resolved_game_card

    game = GameInfo(
        title="Test Game",
        platforms=["PS5"],
        type="FULL_GAME",
        cover_url=None,
        ps_id_suffix="TESTGAME",
    )
    price = RegionPrice(9.99, "USD", None, None, ps_id="TESTGAME")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="tester"),
        answer=AsyncMock(),
        answer_photo=AsyncMock(),
    )
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    user = SimpleNamespace(show_cross_region_saves=True)
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.is_subscribed",
        new=AsyncMock(return_value=None),
    )
    format_card = mocker.patch(
        "bot.handlers.ps_store_link.format_game_card",
        return_value="formatted card",
    )
    session = _session()

    await send_resolved_game_card(
        message,
        state,
        session,
        game,
        {"en-us": price},
        {"USD": 1.0},
        "USD",
    )

    session.commit.assert_awaited_once_with()
    state.set_state.assert_awaited_once_with(SearchForm.showing_results)
    state.update_data.assert_awaited_once_with(
        entries=[{"game": game.to_dict(), "prices": {"en-us": price.to_dict()}}],
        rates={"USD": 1.0},
        base_currency="USD",
    )
    format_card.assert_called_once_with(
        game,
        {"en-us": price},
        {"USD": 1.0},
        footer="Want to track prices in more regions?\nAdd a new one: /add_region",
        base_currency="USD",
        show_cross_region_saves=True,
    )
    message.answer.assert_awaited_once()
    assert message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][
        0
    ].callback_data == "subscribe:0"
    message.answer_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_link_stops_when_no_tracked_regions(mocker):
    """Handler exits when ensure returns empty; DB auto-add covered in integration."""
    from bot.handlers.ps_store_link import on_store_link

    message = _message()
    state = _state()
    user = SimpleNamespace(id=1, preferred_currency=None)
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link._ensure_tracked_regions",
        new=AsyncMock(return_value=[]),
    )
    send_card = mocker.patch(
        "bot.handlers.ps_store_link.send_resolved_game_card",
        new=AsyncMock(),
    )
    get_info = mocker.patch(
        "bot.handlers.ps_store_link.get_game_info",
        new=AsyncMock(),
    )
    session = _session()

    await on_store_link(message, state, session)

    state.clear.assert_awaited_once_with()
    send_card.assert_not_awaited()
    get_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_link_sends_single_game_card(mocker):
    from bot.handlers.ps_store_link import on_store_link

    game = GameInfo(
        title="Test Game",
        platforms=["PS5"],
        type="FULL_GAME",
        cover_url=None,
        ps_id_suffix="TESTGAME00000000",
    )
    price = RegionPrice(9.99, "USD", None, None, ps_id="UP-TEST")
    message = _message()
    state = _state()
    user = SimpleNamespace(
        id=1,
        preferred_currency="EUR",
        show_cross_region_saves=True,
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_user_regions",
        new=AsyncMock(return_value=[SimpleNamespace(code="en-us")]),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_game_info",
        new=AsyncMock(return_value=(game, price)),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.prices_for_tracked_regions",
        new=AsyncMock(return_value={"en-us": price}),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_rates",
        new=AsyncMock(return_value={"USD": 1.0, "EUR": 0.9}),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.is_subscribed",
        new=AsyncMock(return_value=None),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.format_game_card",
        return_value="formatted card",
    )

    await on_store_link(message, state, _session())

    state.clear.assert_awaited_once_with()
    state.set_state.assert_awaited_once_with(SearchForm.showing_results)
    stored_entries = state.update_data.await_args.kwargs["entries"]
    assert len(stored_entries) == 1
    message.answer.assert_awaited_once()
    message.answer_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_link_reports_unresolvable_product(mocker):
    from bot.handlers.ps_store_link import on_store_link

    message = _message()
    state = _state()
    user = SimpleNamespace(id=1, preferred_currency=None)
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_user_regions",
        new=AsyncMock(return_value=[SimpleNamespace(code="en-us")]),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_game_info",
        new=AsyncMock(return_value=None),
    )

    await on_store_link(message, state, _session())

    state.clear.assert_awaited_once_with()
    message.answer.assert_awaited_once_with(
        "Couldn't open this PS Store link."
    )


@pytest.mark.asyncio
async def test_concept_link_with_one_edition_sends_card_without_picker(mocker):
    from bot.handlers.ps_store_link import on_store_link

    game = GameInfo(
        title="Test Game",
        platforms=["PS5"],
        type="FULL_GAME",
        cover_url=None,
        ps_id_suffix="TESTGAME",
    )
    seed_price = RegionPrice(9.99, "USD", None, None, ps_id="UP-TEST")
    regional_price = RegionPrice(8.99, "USD", None, None, ps_id="UP-TEST")
    message = _message(CONCEPT_URL)
    state = _state()
    user = SimpleNamespace(id=1, preferred_currency="EUR")
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_user_regions",
        new=AsyncMock(return_value=[SimpleNamespace(code="en-us")]),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.list_concept_editions",
        new=AsyncMock(return_value=[(game, seed_price)]),
    )
    prices = mocker.patch(
        "bot.handlers.ps_store_link.prices_for_tracked_regions",
        new=AsyncMock(return_value={"en-us": regional_price}),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_rates",
        new=AsyncMock(return_value={"USD": 1.0, "EUR": 0.9}),
    )
    send_card = mocker.patch(
        "bot.handlers.ps_store_link.send_resolved_game_card",
        new=AsyncMock(),
    )

    await on_store_link(message, state, _session())

    state.clear.assert_awaited_once_with()
    prices.assert_awaited_once_with(game, "UP-TEST", "en-us", ["en-us"])
    send_card.assert_awaited_once()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_concept_link_with_two_editions_shows_picker(mocker):
    from bot.handlers.ps_store_link import on_store_link

    games = [
        GameInfo("Test Game", ["PS5"], "FULL_GAME", None, "STANDARD"),
        GameInfo("Test Game Deluxe", ["PS5"], "PREMIUM_EDITION", None, "DELUXE"),
    ]
    editions = [
        (games[0], RegionPrice(9.99, "USD", None, None, ps_id="UP-STANDARD")),
        (games[1], RegionPrice(19.99, "USD", None, None, ps_id="UP-DELUXE")),
    ]
    message = _message(CONCEPT_URL)
    state = _state()
    user = SimpleNamespace(id=1, preferred_currency="EUR")
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_user_regions",
        new=AsyncMock(return_value=[SimpleNamespace(code="en-us")]),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.list_concept_editions",
        new=AsyncMock(return_value=editions),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_rates",
        new=AsyncMock(return_value={"USD": 1.0, "EUR": 0.9}),
    )

    await on_store_link(message, state, _session())

    state.clear.assert_awaited_once_with()
    state.set_state.assert_awaited_once_with(SearchForm.showing_results)
    state.update_data.assert_awaited_once_with(
        link_editions=[
            {"game": games[0].to_dict(), "seed_ps_id": "UP-STANDARD"},
            {"game": games[1].to_dict(), "seed_ps_id": "UP-DELUXE"},
        ],
        link_locale="en-us",
        rates={"USD": 1.0, "EUR": 0.9},
        base_currency="EUR",
    )
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args == ("Choose edition:",)
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert [row[0].callback_data for row in markup.inline_keyboard] == [
        "link_edition:0",
        "link_edition:1",
    ]


@pytest.mark.asyncio
async def test_link_edition_callback_sends_second_edition_as_entry_zero(mocker):
    from bot.handlers.ps_store_link import on_link_edition

    games = [
        GameInfo("Standard", ["PS5"], "FULL_GAME", None, "STANDARD"),
        GameInfo("Deluxe", ["PS5"], "PREMIUM_EDITION", None, "DELUXE"),
    ]
    data = {
        "link_editions": [
            {"game": games[0].to_dict(), "seed_ps_id": "UP-STANDARD"},
            {"game": games[1].to_dict(), "seed_ps_id": "UP-DELUXE"},
        ],
        "link_locale": "en-us",
        "rates": {"USD": 1.0},
        "base_currency": "USD",
    }
    message = _message()
    callback = SimpleNamespace(
        data="link_edition:1",
        from_user=message.from_user,
        message=message,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value=data),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    user = SimpleNamespace(id=1, show_cross_region_saves=True)
    price = RegionPrice(19.99, "USD", None, None, ps_id="UP-DELUXE")
    mocker.patch(
        "bot.handlers.ps_store_link.get_or_create_user",
        new=AsyncMock(return_value=user),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.get_user_regions",
        new=AsyncMock(return_value=[SimpleNamespace(code="en-us")]),
    )
    prices = mocker.patch(
        "bot.handlers.ps_store_link.prices_for_tracked_regions",
        new=AsyncMock(return_value={"en-us": price}),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.is_subscribed",
        new=AsyncMock(return_value=None),
    )
    mocker.patch("bot.handlers.ps_store_link.format_game_card", return_value="card")
    session = _session()

    await on_link_edition(callback, state, session)

    assert session.commit.await_count == 2
    callback.answer.assert_awaited_once_with()
    prices.assert_awaited_once_with(games[1], "UP-DELUXE", "en-us", ["en-us"])
    stored_entries = state.update_data.await_args.kwargs["entries"]
    assert stored_entries == [
        {
            "game": games[1].to_dict(),
            "prices": {"en-us": price.to_dict()},
        }
    ]
    assert message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][
        0
    ].callback_data == "subscribe:0"
