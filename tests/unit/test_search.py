from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.search import _best_ps_id, _do_search
from services.ps_store import GameResult

UP_ID = "UP9000-PPSA03016_00-GAME"
EP_ID = "EP9000-CUSA12345_00-GAME"
JP_ID = "JP9000-PPSA99999_00-GAME"
KP_ID = "KP9000-PPSA00001_00-GAME"


# --- _best_ps_id ---

def test_best_ps_id_eu_prefers_ep():
    ps_ids = {"en-us": UP_ID, "en-gb": EP_ID}
    assert _best_ps_id("en-pl", ps_ids) == EP_ID

def test_best_ps_id_us_prefers_up():
    ps_ids = {"en-gb": EP_ID, "en-us": UP_ID}
    assert _best_ps_id("en-us", ps_ids) == UP_ID

def test_best_ps_id_jp_prefers_jp():
    ps_ids = {"en-gb": EP_ID, "ja-jp": JP_ID}
    assert _best_ps_id("ja-jp", ps_ids) == JP_ID

def test_best_ps_id_kr_prefers_kp():
    ps_ids = {"en-gb": EP_ID, "ko-kr": KP_ID}
    assert _best_ps_id("ko-kr", ps_ids) == KP_ID

def test_best_ps_id_eu_no_ep_returns_none():
    assert _best_ps_id("en-pl", {"en-us": UP_ID}) is None

def test_best_ps_id_us_no_up_returns_none():
    assert _best_ps_id("en-us", {"en-gb": EP_ID}) is None

def test_best_ps_id_empty_returns_none():
    assert _best_ps_id("en-gb", {}) is None

def test_best_ps_id_multiple_ep_returns_first():
    ps_ids = {"en-gb": EP_ID, "en-pl": "EP1111-CUSA00000_00-OTHER"}
    result = _best_ps_id("de-de", ps_ids)
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
    return GameResult(
        ps_id=ps_id, title=title, platforms=["PS5"], type="FULL_GAME",
        price=price, currency=currency, base_price=None, discount_text=None, cover_url=None,
    )

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
async def test_free_games_excluded_from_results(mocker, common_mocks):
    """Games with no price in any region (free/demo) should not appear in the list."""
    regions = [_region("en-us")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    paid_game = _make_game(UP_ID, title="Paid Game", price=39.99, currency="$")
    free_game = _make_game("UP9000-PPSA99999_00-FREE", title="Free Game Demo", price=None, currency=None)
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock, return_value=[paid_game, free_game])
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "game")

    entries = captured.get("entries", [])
    titles = [e["game"]["title"] for e in entries]
    assert "Paid Game" in titles
    assert "Free Game Demo" not in titles


@pytest.mark.asyncio
async def test_free_game_excluded_after_fallback(mocker, common_mocks):
    """Game found via fallback with price=None should still be excluded."""
    regions = [_region("en-gb"), _region("de-de")]
    mocker.patch("bot.handlers.search.get_user_regions", new_callable=AsyncMock, return_value=regions)

    free_game = _make_game(EP_ID, title="Free Demo", price=None, currency=None)
    mocker.patch("bot.handlers.search.search_games", new_callable=AsyncMock, side_effect=[[free_game], []])

    fallback_free = _make_game(EP_ID, title="Free Demo", price=None, currency=None)
    mocker.patch("bot.handlers.search.get_game_info", new_callable=AsyncMock, return_value=fallback_free)

    state = AsyncMock()
    captured = {}
    state.update_data = AsyncMock(side_effect=lambda **kw: captured.update(kw))

    await _do_search(_make_message(), state, AsyncMock(), "free demo")

    entries = captured.get("entries", [])
    assert len(entries) == 0


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
