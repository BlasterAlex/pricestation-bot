from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.search import _do_search, on_game_select
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
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock,
                 side_effect=[[cyrillic_game], [ascii_game]])
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
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock,
                 side_effect=[[cyrillic_game]])
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "final fantasy")

    entries = captured.get("entries", [])
    assert len(entries) == 1
    assert entries[0]["game"]["title"] == "Набір FINAL FANTASY VII REMAKE & REBIRTH Twin Pack"


# --- fallback helpers ---

def _make_game(ps_id, title="Test Game", price=49.99, currency="€"):
    game = GameInfo(title=title, platforms=["PS5"], type="FULL_GAME", cover_url=None)
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
    mock_search.side_effect = [[game], []]

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
    mock_search.side_effect = [[game_ep], [game_de]]

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
    mock_search.side_effect = [[game], [], []]

    mock_get_info = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=None)

    await _do_search(_make_message(), AsyncMock(), AsyncMock(), "test game")

    assert mock_get_info.call_count == 2
    calls = {call.args for call in mock_get_info.call_args_list}
    assert calls == {(EP_ID, "de-de"), (EP_ID, "fr-fr")}



@pytest.mark.asyncio
async def test_fallback_result_merged_into_prices(mocker, common_mocks):
    """Successful fallback adds the region's price to by_title, which ends up in FSM state."""
    regions = [_region("en-gb"), _region("de-de")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    game = _make_game(EP_ID, price=49.99, currency="€")
    mock_search = mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock)
    mock_search.side_effect = [[game], []]

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


def _make_entry(ps_id: str, base_price: float | None = None, discount_end: str | None = None) -> dict:
    game = GameInfo(title="Test Game", platforms=["PS5"], type="FULL_GAME", cover_url=None)
    rp = RegionPrice(price=29.99, currency="€", base_price=base_price,
                     discount_text="-40%" if base_price else None, ps_id=ps_id, discount_end=discount_end)
    return {"game": game.to_dict(), "prices": {"en-gb": rp.to_dict()}}


@pytest.fixture
def select_mocks(mocker):
    mocker.patch("bot.handlers.search.is_subscribed", new_callable=AsyncMock, return_value=False)
    mocker.patch("bot.handlers.search.format_game_card", return_value="caption")
    mocker.patch("bot.handlers.search.game_card_keyboard", return_value=MagicMock())


@pytest.mark.asyncio
async def test_on_game_select_saves_discount_end_to_state(mocker, select_mocks):
    """discount_end fetched via get_game_info must be written back into FSM state entries."""
    entry = _make_entry(EP_ID, base_price=49.99)
    assert entry["prices"]["en-gb"]["discount_end"] is None

    state = AsyncMock()
    captured = {}
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    info_rp = RegionPrice(price=29.99, currency="€", base_price=49.99,
                          discount_text="-40%", ps_id=EP_ID, discount_end="2025-06-01 23:59")
    mocker.patch("bot.handlers.search.get_game_info",
                 new_callable=AsyncMock, return_value=(MagicMock(), info_rp))

    await on_game_select(_make_callback(0), state, AsyncMock())

    assert "entries" in captured
    assert captured["entries"][0]["prices"]["en-gb"]["discount_end"] == "2025-06-01 23:59"


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


@pytest.mark.asyncio
async def test_on_game_select_skips_fetch_when_no_discount(mocker, select_mocks):
    """Game has no discount → get_game_info must not be called."""
    entry = _make_entry(EP_ID, base_price=None)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entries": [entry], "rates": {}})

    mock_get = mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    await on_game_select(_make_callback(0), state, AsyncMock())

    mock_get.assert_not_called()
