from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.search import _do_search, cmd_search, on_game_select, on_search_query
from bot.states.subscription import SearchForm
from services.ps_store import GameInfo, RegionPrice, best_ps_id

UP_ID = "UP9000-PPSA03016_00-GAME"
EP_ID = "EP9000-CUSA12345_00-GAME"
JP_ID = "JP9000-PPSA99999_00-GAME"
KP_ID = "KP9000-PPSA00001_00-GAME"


# --- best_ps_id (from services.ps_store) ---

def testbest_ps_id_eu_prefers_ep():
    ps_ids = {"en-us": UP_ID, "en-gb": EP_ID}
    assert best_ps_id("en-pl", ps_ids) == EP_ID

def testbest_ps_id_us_prefers_up():
    ps_ids = {"en-gb": EP_ID, "en-us": UP_ID}
    assert best_ps_id("en-us", ps_ids) == UP_ID

def testbest_ps_id_jp_prefers_jp():
    ps_ids = {"en-gb": EP_ID, "ja-jp": JP_ID}
    assert best_ps_id("ja-jp", ps_ids) == JP_ID

def testbest_ps_id_kr_prefers_kp():
    ps_ids = {"en-gb": EP_ID, "ko-kr": KP_ID}
    assert best_ps_id("ko-kr", ps_ids) == KP_ID

def testbest_ps_id_eu_no_ep_returns_none():
    assert best_ps_id("en-pl", {"en-us": UP_ID}) is None

def testbest_ps_id_us_no_up_returns_none():
    assert best_ps_id("en-us", {"en-gb": EP_ID}) is None

def testbest_ps_id_empty_returns_none():
    assert best_ps_id("en-gb", {}) is None

def testbest_ps_id_multiple_ep_returns_first():
    ps_ids = {"en-gb": EP_ID, "en-pl": "EP1111-CUSA00000_00-OTHER"}
    result = best_ps_id("de-de", ps_ids)
    assert result is not None
    assert result.startswith("EP")


# --- rep_game title selection ---

@pytest.mark.asyncio
async def test_ascii_title_preferred_over_cyrillic(mocker, common_mocks):
    """ASCII title from a later region should replace a non-ASCII title found first."""
    regions = [_region("uk-ua"), _region("en-gb")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    cyrillic_game = _make_game(EP_ID, title="Набір FINAL FANTASY VII REMAKE & REBIRTH Twin Pack")
    ascii_game = _make_game(EP_ID, title="FINAL FANTASY VII REMAKE & REBIRTH Twin Pack")
    # needs_us=True (uk-ua, en-gb don't include en-us) → extra call for en-us canonical
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock,
                 side_effect=[[cyrillic_game], [ascii_game], []])
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "final fantasy")

    entries = captured.get("entries", [])
    assert len(entries) == 1
    assert entries[0]["game"]["title"] == "FINAL FANTASY VII REMAKE & REBIRTH Twin Pack"


@pytest.mark.asyncio
async def test_non_ascii_title_kept_when_no_ascii_alternative(mocker, common_mocks):
    """If only non-ASCII title exists (regional exclusive), it should still be shown."""
    regions = [_region("uk-ua")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    cyrillic_game = _make_game(EP_ID, title="Набір FINAL FANTASY VII REMAKE & REBIRTH Twin Pack")
    # needs_us=True (uk-ua doesn't include en-us) → extra call for en-us canonical
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock,
                 side_effect=[[cyrillic_game], []])
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "final fantasy")

    entries = captured.get("entries", [])
    assert len(entries) == 1
    assert entries[0]["game"]["title"] == "Набір FINAL FANTASY VII REMAKE & REBIRTH Twin Pack"


# --- suffix merge ---

@pytest.mark.asyncio
async def test_suffix_merge_collapses_localized_variants(mocker, common_mocks):
    """Two regions return the same game with different localized titles but same ps_id_suffix → one card."""
    regions = [_region("en-gb"), _region("es-mx")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    en_game = _make_game(
        "EP0006-PPSA20049_00-25STANDARDBUNDLE",
        title="FC 25 Standard Edition PS5",
        ps_id_suffix="25STANDARDBUNDLE",
    )
    es_game = _make_game(
        "EP0006-PPSA20050_00-25STANDARDBUNDLE",
        title="FC 25 Edición Estándar PS5",
        ps_id_suffix="25STANDARDBUNDLE",
    )

    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    # needs_us=True (en-gb, es-mx don't include en-us) → extra call for en-us canonical
    mock_search.side_effect = [[en_game], [es_game], []]

    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "fc 25")

    entries = captured.get("entries", [])
    assert len(entries) == 1, "Same suffix → one card, not two"
    prices = entries[0]["prices"]
    assert "en-gb" in prices
    assert "es-mx" in prices


# --- fallback helpers ---

def _make_game(ps_id, title="Test Game", price=49.99, currency="€", ps_id_suffix=None):
    game = GameInfo(title=title, platforms=["PS5"], type="FULL_GAME", cover_url=None, ps_id_suffix=ps_id_suffix)
    region_price = RegionPrice(price=price, currency=currency, base_price=None, discount_text=None, ps_id=ps_id)
    return game, region_price

def _region(code):
    r = MagicMock()
    r.code = code
    return r

def _make_message():
    msg = AsyncMock()
    msg.from_user = MagicMock(id=1, username="user")
    return msg

@pytest.fixture
def common_mocks(mocker):
    mocker.patch("bot.handlers.search.get_or_create_user", new_callable=AsyncMock)
    mocker.patch("bot.handlers.search.get_rates", new_callable=AsyncMock, return_value={})
    mocker.patch("bot.handlers.search.format_game_list", return_value="text")
    mocker.patch("bot.handlers.search.search_results_keyboard", return_value=MagicMock())


# --- fallback: get_game_info calls ---

@pytest.mark.asyncio
async def test_fallback_fires_for_missing_eu_region(mocker, common_mocks):
    """en-gb finds game (EP id); de-de misses → fallback fetches EP id for de-de."""
    regions = [_region("en-gb"), _region("de-de")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game = _make_game(EP_ID)
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    # needs_us=True (en-gb, de-de don't include en-us) → extra call for en-us canonical
    mock_search.side_effect = [[game], [], []]

    mock_get_info = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=None)

    await _do_search(_make_message(), AsyncMock(), AsyncMock(), "test game")

    mock_get_info.assert_called_once_with(EP_ID, "de-de")


@pytest.mark.asyncio
async def test_fallback_not_fired_when_prefix_unavailable(mocker, common_mocks):
    """en-us finds game (UP id); en-gb misses → no EP id available → no fallback."""
    regions = [_region("en-us"), _region("en-gb")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game = _make_game(UP_ID)
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    mock_search.side_effect = [[game], []]

    mock_get_info = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    await _do_search(_make_message(), AsyncMock(), AsyncMock(), "test game")

    mock_get_info.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_not_fired_when_all_regions_found(mocker, common_mocks):
    """Both regions return the game → no fallback needed."""
    regions = [_region("en-gb"), _region("de-de")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game_ep = _make_game(EP_ID)
    game_de = _make_game("EP9000-CUSA12345_00-GAME-DE")
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    # needs_us=True (en-gb, de-de don't include en-us) → extra call for en-us canonical
    mock_search.side_effect = [[game_ep], [game_de], []]

    mock_get_info = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    await _do_search(_make_message(), AsyncMock(), AsyncMock(), "test game")

    mock_get_info.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_fires_per_region(mocker, common_mocks):
    """en-gb finds game (EP id); de-de and fr-fr both miss → get_game_info called for each missing region."""
    regions = [_region("en-gb"), _region("de-de"), _region("fr-fr")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game = _make_game(EP_ID)
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    # needs_us=True (en-gb, de-de, fr-fr don't include en-us) → extra call for en-us canonical
    mock_search.side_effect = [[game], [], [], []]

    mock_get_info = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=None)

    await _do_search(_make_message(), AsyncMock(), AsyncMock(), "test game")

    assert mock_get_info.call_count == 2
    calls = {call.args for call in mock_get_info.call_args_list}
    assert calls == {(EP_ID, "de-de"), (EP_ID, "fr-fr")}



@pytest.mark.asyncio
async def test_fallback_result_merged_into_prices(mocker, common_mocks):
    """Successful fallback adds the region's price to by_key, which ends up in FSM state."""
    regions = [_region("en-gb"), _region("de-de")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game = _make_game(EP_ID, price=49.99, currency="€")
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    # needs_us=True (en-gb, de-de don't include en-us) → extra call for en-us canonical
    mock_search.side_effect = [[game], [], []]

    fallback_game = _make_game(EP_ID, price=39.99, currency="€")
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=fallback_game)

    state = AsyncMock()
    captured = {}

    async def capture_update_data(**kwargs):
        captured.update(kwargs)

    state.update_data = AsyncMock(side_effect=capture_update_data)

    await _do_search(_make_message(), state, AsyncMock(), "test game")

    entries = captured.get("entries", [])
    assert len(entries) == 1
    prices = entries[0]["prices"]
    assert "de-de" in prices
    assert prices["de-de"]["price"] == 39.99


# --- on_game_select: discount_end persistence ---

def _make_callback(index: int, user_id: int = 1) -> AsyncMock:
    cb = AsyncMock()
    cb.data = f"game_select:{index}"
    cb.from_user = MagicMock(id=user_id)
    cb.message = AsyncMock()
    return cb


def _make_entry(ps_id: str, base_price: float | None = None, discount_end: datetime | None = None) -> dict:
    game = GameInfo(title="Test Game", platforms=["PS5"], type="FULL_GAME", cover_url=None)
    rp = RegionPrice(price=29.99, currency="€", base_price=base_price,
                     discount_text="-40%" if base_price else None, ps_id=ps_id, discount_end=discount_end)
    return {"game": game.to_dict(), "prices": {"en-gb": rp.to_dict()}}


@pytest.fixture
def select_mocks(mocker):
    user = MagicMock()
    user.show_cross_region_saves = True
    mocker.patch("bot.handlers.search.get_or_create_user", new_callable=AsyncMock, return_value=user)
    mocker.patch("bot.handlers.search.is_subscribed", new_callable=AsyncMock, return_value=None)
    mocker.patch("bot.handlers.search.format_game_card", return_value="caption")
    mocker.patch("bot.handlers.search.subscribe_keyboard", return_value=MagicMock())
    mocker.patch("bot.handlers.search.unsubscribe_keyboard", return_value=MagicMock())


@pytest.mark.asyncio
async def test_on_game_select_saves_discount_end_to_state(mocker, select_mocks):
    """discount_end fetched via get_game_info must be written back into FSM state entries."""
    entry = _make_entry(EP_ID, base_price=49.99)
    assert entry["prices"]["en-gb"]["discount_end"] is None

    state = AsyncMock()
    captured = {}
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    end = datetime(2025, 6, 1, 23, 59, tzinfo=timezone.utc)
    info_rp = RegionPrice(
        price=29.99, currency="€", base_price=49.99,
        discount_text="-40%", ps_id=EP_ID, discount_end=end,
    )
    mocker.patch("bot.handlers.search.get_game_info",
                 new_callable=AsyncMock, return_value=(MagicMock(), info_rp))

    await on_game_select(_make_callback(0), state, AsyncMock())

    assert "entries" in captured
    assert captured["entries"][0]["prices"]["en-gb"]["discount_end"] == end


@pytest.mark.asyncio
async def test_on_game_select_skips_state_update_when_no_discount_end(mocker, select_mocks):
    """If get_game_info returns no discount_end, state must not be updated."""
    entry = _make_entry(EP_ID, base_price=49.99)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})

    info_rp = RegionPrice(price=29.99, currency="€", base_price=49.99,
                          discount_text="-40%", ps_id=EP_ID, discount_end=None)
    mocker.patch("bot.handlers.search.get_game_info",
                 new_callable=AsyncMock, return_value=(MagicMock(), info_rp))

    await on_game_select(_make_callback(0), state, AsyncMock())

    state.update_data.assert_not_called()


# --- _do_search: no regions ---


@pytest.mark.asyncio
async def test_do_search_no_regions_answers_with_hint(mocker, common_mocks):
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=[])
    msg = _make_message()

    await _do_search(msg, AsyncMock(), AsyncMock(), "god of war")

    msg.answer.assert_called_once()
    assert "region" in msg.answer.call_args.args[0].lower()


# --- cmd_search ---


@pytest.mark.asyncio
async def test_cmd_search_without_query_sets_fsm_state(mocker):
    msg = AsyncMock()
    msg.text = "/search"
    state = AsyncMock()

    await cmd_search(msg, state, AsyncMock())

    state.set_state.assert_called_once_with(SearchForm.waiting_for_query)
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_search_with_query_calls_do_search(mocker, common_mocks):
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=[])
    msg = AsyncMock()
    msg.text = "/search god of war"
    msg.from_user = MagicMock(id=1, username="user")
    state = AsyncMock()

    await cmd_search(msg, state, AsyncMock())

    # _do_search called → no regions → answers with hint
    msg.answer.assert_called_once()
    state.set_state.assert_not_called()


# --- on_search_query ---


@pytest.mark.asyncio
async def test_on_search_query_delegates_to_do_search(mocker, common_mocks):
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=[])
    msg = _make_message()
    msg.text = "  god of war  "

    await on_search_query(msg, AsyncMock(), AsyncMock())

    msg.answer.assert_called_once()  # no regions → hint message


@pytest.mark.asyncio
async def test_on_search_query_ignores_empty_text(mocker):
    mock_do = mocker.patch("bot.handlers.search._do_search", new_callable=AsyncMock)
    msg = AsyncMock()
    msg.text = "   "

    await on_search_query(msg, AsyncMock(), AsyncMock())

    mock_do.assert_not_called()


# --- on_game_select: edge cases ---


@pytest.mark.asyncio
async def test_on_game_select_out_of_bounds_answers_not_found(mocker, select_mocks):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entries": [], "rates": {}})
    cb = _make_callback(5)

    await on_game_select(cb, state, AsyncMock())

    cb.message.answer.assert_called_once()
    assert "not found" in cb.message.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_on_game_select_sends_photo_when_cover_url_set(mocker, select_mocks):
    game = GameInfo(
        title="Test Game", platforms=["PS5"], type="FULL_GAME",
        cover_url="https://example.com/cover.jpg",
    )
    rp = RegionPrice(price=29.99, currency="€", base_price=None, discount_text=None, ps_id=EP_ID)
    entry = {"game": game.to_dict(), "prices": {"en-gb": rp.to_dict()}}

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=(game, rp))

    cb = _make_callback(0)
    await on_game_select(cb, state, AsyncMock())

    cb.message.answer_photo.assert_called_once()
    cb.message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_on_game_select_skips_fetch_when_no_discount(mocker, select_mocks):
    """Game has no discount → get_game_info must not be called."""
    entry = _make_entry(EP_ID, base_price=None)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})

    mock_get = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    await on_game_select(_make_callback(0), state, AsyncMock())

    mock_get.assert_not_called()
