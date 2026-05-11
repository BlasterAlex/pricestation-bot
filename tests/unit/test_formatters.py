from bot.formatters import (
    _card_price_lines,
    _format_price,
    _game_header,
    _price_line,
    format_game_card,
    format_game_list,
    locale_flag,
)
from services.ps_store import GameResult

RATES = {"EUR": 0.92, "INR": 84.0, "TRY": 45.0}

PS_ID = "UP9000-PPSA03016_00-GAME"

GAME = GameResult(
    ps_id=PS_ID,
    title="Test Game",
    platforms=["PS5"],
    type="FULL_GAME",
    price=59.99,
    currency="€",
    base_price=None,
    discount_text=None,
    cover_url=None,
)


# --- locale_flag ---

def test_locale_flag_us():
    assert locale_flag("en-us") == "🇺🇸"


def test_locale_flag_in():
    assert locale_flag("en-in") == "🇮🇳"


def test_locale_flag_gb():
    assert locale_flag("en-gb") == "🇬🇧"


# --- _format_price ---

def test_format_price_symbol_whole():
    assert _format_price(5.0, "€") == "€5"


def test_format_price_symbol_decimal():
    assert _format_price(5.99, "€") == "€5.99"


def test_format_price_alpha_whole():
    assert _format_price(2799.0, "TL") == "TL 2799"


def test_format_price_alpha_decimal():
    assert _format_price(2799.50, "TL") == "TL 2799.50"


# --- _game_header ---

def test_game_header_full_game():
    lines = _game_header(GAME)
    assert lines[0] == "🎮 Test Game"
    assert lines[1] == "PS5 · Full Game"


def test_game_header_premium_edition():
    game = GameResult(**{**GAME.__dict__, "type": "PREMIUM_EDITION", "platforms": ["PS4", "PS5"]})
    lines = _game_header(game)
    assert lines[0].startswith("💎")
    assert "Premium Edition" in lines[1]
    assert "PS4 · PS5" in lines[1]


def test_game_header_unknown_type():
    game = GameResult(**{**GAME.__dict__, "type": "UNKNOWN_TYPE"})
    lines = _game_header(game)
    assert lines[0].startswith("🎮")
    assert "UNKNOWN_TYPE" in lines[1]


def test_game_header_no_platforms():
    game = GameResult(**{**GAME.__dict__, "platforms": []})
    lines = _game_header(game)
    assert lines[1].startswith("—")


# --- _price_line (list view) ---

def test_price_line_single_region_no_bold():
    prices = {"en-us": (9.99, "$", None, None)}
    result = _price_line(prices, RATES)
    assert "<b>" not in result


def test_price_line_cheapest_is_bold():
    prices = {
        "en-gb": (49.99, "£", None, None),
        "en-in": (4999.0, "Rs", None, None),
    }
    result = _price_line(prices, RATES)
    # Rs 4999 / 84 ≈ $59.51, £49.99 / rates["GBP"] — GBP not in RATES so usd=None
    # only en-in has usd, so it's cheapest and bold
    assert "<b>" in result
    assert result.index("<b>") < result.index("Rs")


def test_price_line_no_usd_for_usd_currency():
    prices = {"en-us": (9.99, "$", None, None)}
    result = _price_line(prices, RATES)
    assert "($" not in result


def test_price_line_usd_shown_for_non_usd():
    prices = {"en-gb": (59.99, "€", None, None)}
    result = _price_line(prices, RATES)
    assert "($" in result


def test_price_line_na_when_no_amount():
    prices = {"en-us": (None, None, None, None)}
    result = _price_line(prices, RATES)
    assert "N/A" in result


def test_price_line_shows_strike_for_base_price():
    prices = {"en-gb": (39.99, "€", 59.99, "-33%")}
    result = _price_line(prices, RATES)
    assert "<s>" in result
    assert "-33%" in result


def test_price_line_with_link():
    prices = {"en-us": (9.99, "$", None, None)}
    result = _price_line(prices, RATES, with_link=True, ps_id=PS_ID)
    assert f"https://store.playstation.com/en-us/product/{PS_ID}" in result


# --- _card_price_lines ---

def test_card_price_lines_has_link():
    prices = {"en-us": (9.99, "$", None, None)}
    lines = _card_price_lines(PS_ID, prices, RATES)
    assert f"https://store.playstation.com/en-us/product/{PS_ID}" in lines[0]


def test_card_price_lines_single_region_no_bold():
    prices = {"en-us": (9.99, "$", None, None)}
    lines = _card_price_lines(PS_ID, prices, RATES)
    assert "<b>" not in lines[0]


def test_card_price_lines_cheapest_bold_wraps_link_only():
    prices = {
        "en-gb": (59.99, "€", None, None),
        "en-in": (4999.0, "Rs", None, None),
    }
    lines = _card_price_lines(PS_ID, prices, RATES)
    in_line = next(line for line in lines if "Rs" in line)
    # bold should close before the end of line (old price part must be outside)
    assert in_line.startswith("🇮🇳 <b><a href=")
    assert "</b>" in in_line
    bold_end = in_line.index("</b>")
    assert in_line.find("</a>") <= bold_end + len("</b>") + 1


def test_card_price_lines_no_old_price():
    prices = {"en-us": (9.99, "$", None, None)}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=None)
    assert "↓" not in lines[0]
    assert "↑" not in lines[0]


def test_card_price_lines_price_drop_arrow():
    prices = {"en-gb": (39.99, "€", None, None)}
    old = {"en-gb": (59.99, "€")}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=old)
    assert "↓" in lines[0]
    assert "<s>" in lines[0]


def test_card_price_lines_price_increase_arrow():
    prices = {"en-gb": (69.99, "€", None, None)}
    old = {"en-gb": (59.99, "€")}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=old)
    assert "↑" in lines[0]
    assert "<s>" in lines[0]


def test_card_price_lines_no_arrow_when_price_unchanged():
    prices = {"en-gb": (59.99, "€", None, None)}
    old = {"en-gb": (59.99, "€")}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=old)
    assert "↓" not in lines[0]
    assert "↑" not in lines[0]


def test_card_price_lines_old_usd_shown():
    prices = {"en-gb": (39.99, "€", None, None)}
    old = {"en-gb": (59.99, "€")}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=old)
    # old price in EUR → should show USD equivalent in strikethrough
    assert "($" in lines[0]


def test_card_price_lines_no_old_usd_for_usd():
    prices = {"en-us": (7.99, "$", None, None)}
    old = {"en-us": (9.99, "$")}
    lines = _card_price_lines(PS_ID, prices, RATES, old_prices=old)
    assert "↓" in lines[0]
    # no USD conversion for USD prices
    old_part = lines[0].split("↓")[1]
    assert "($" not in old_part


# --- format_game_list ---

def test_format_game_list_empty():
    result = format_game_list("Title", "Footer", [], {})
    assert result == "Nothing found. Try a different query."


def test_format_game_list_structure():
    prices = {PS_ID: {"en-us": (9.99, "$", None, None)}}
    result = format_game_list("My Games", "The end", [GAME], prices, RATES)
    assert result.startswith("My Games")
    assert result.endswith("The end")
    assert "Test Game" in result


def test_format_game_list_no_prices():
    result = format_game_list("Title", "Footer", [GAME], {}, RATES)
    assert "Test Game" in result


# --- format_game_card ---

def test_format_game_card_structure():
    prices = {"en-in": (4999.0, "Rs", None, None)}
    result = format_game_card(GAME, prices, RATES, title="Details:", footer="Add region: /add_region")
    assert result.startswith("Details:")
    assert result.endswith("Add region: /add_region")
    assert "Test Game" in result
    assert "Prices by region:" in result


def test_format_game_card_no_prices_no_header():
    result = format_game_card(GAME, {}, RATES)
    assert "Prices by region:" not in result


def test_format_game_card_with_old_prices():
    prices = {"en-in": (3999.0, "Rs", None, None)}
    old = {"en-in": (4999.0, "Rs")}
    result = format_game_card(GAME, prices, RATES, old_prices=old)
    assert "↓" in result
    assert "<s>" in result
