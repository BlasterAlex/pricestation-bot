import dataclasses
from datetime import datetime, timezone

from bot.formatters import (
    _card_price_lines,
    _format_offer_end,
    _format_price,
    _format_save_compatibility_line,
    _game_header,
    _offer_end_line,
    _price_line,
    format_game_card,
    format_game_list,
    locale_flag,
)
from services.ps_store import GameInfo, RegionPrice

RATES = {"EUR": 0.92, "INR": 84.0, "TRY": 45.0}

PS_ID = "UP9000-PPSA03016_00-GAME"
EP_ID = "EP9000-CUSA00001_00-GAME"
US_CONTROL = "UP4040-PPSA01949_00-CONTROLUEPS50000"
BR_CONTROL = "UP4040-PPSA01949_00-CONTROLBR0000000"
TR_CONTROL = "EP4040-PPSA01951_00-CONTROLTR0000000"

GAME = GameInfo(
    title="Test Game",
    platforms=["PS5"],
    type="FULL_GAME",
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
    game = dataclasses.replace(GAME, type="PREMIUM_EDITION", platforms=["PS4", "PS5"])
    lines = _game_header(game)
    assert lines[0].startswith("💎")
    assert "Premium Edition" in lines[1]
    assert "PS4 · PS5" in lines[1]


def test_game_header_unknown_type():
    game = dataclasses.replace(GAME, type="UNKNOWN_TYPE")
    lines = _game_header(game)
    assert lines[0].startswith("🎮")
    assert "UNKNOWN_TYPE" in lines[1]


def test_game_header_no_platforms():
    game = dataclasses.replace(GAME, platforms=[])
    lines = _game_header(game)
    assert lines[1].startswith("—")


# --- _price_line (list view) ---

def test_price_line_single_region_no_bold():
    prices = {"en-us": RegionPrice(9.99, "$", None, None)}
    result = _price_line(prices, RATES)
    assert "<b>" not in result


def test_price_line_cheapest_is_bold():
    prices = {
        "en-gb": RegionPrice(49.99, "£", None, None),
        "en-in": RegionPrice(4999.0, "Rs", None, None),
    }
    result = _price_line(prices, RATES)
    # Rs 4999 / 84 ≈ $59.51, £49.99 — GBP not in RATES so usd=None
    # only en-in has usd, so it's cheapest and bold
    assert "<b>" in result
    assert result.index("<b>") < result.index("Rs")


def test_price_line_no_usd_for_usd_currency():
    prices = {"en-us": RegionPrice(9.99, "$", None, None)}
    result = _price_line(prices, RATES)
    assert "($" not in result


def test_price_line_usd_shown_for_non_usd():
    prices = {"en-gb": RegionPrice(59.99, "€", None, None)}
    result = _price_line(prices, RATES)
    assert "($" in result


def test_price_line_na_when_no_amount():
    prices = {"en-us": RegionPrice(None, None, None, None)}
    result = _price_line(prices, RATES)
    assert "N/A" in result


def test_price_line_shows_strike_for_base_price():
    prices = {"en-gb": RegionPrice(39.99, "€", 59.99, "-33%")}
    result = _price_line(prices, RATES)
    assert "<s>" in result
    assert "-33%" in result


# --- _card_price_lines ---

def test_card_price_lines_has_link():
    prices = {"en-us": RegionPrice(9.99, "$", None, None, ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES)
    assert f"https://store.playstation.com/en-us/product/{PS_ID}" in lines[0]


def test_card_price_lines_single_region_no_bold():
    prices = {"en-us": RegionPrice(9.99, "$", None, None, ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES)
    assert "<b>" not in lines[0]


def test_card_price_lines_cheapest_bold_wraps_link_only():
    prices = {
        "en-gb": RegionPrice(59.99, "€", None, None, ps_id=EP_ID),
        "en-in": RegionPrice(4999.0, "Rs", None, None, ps_id=EP_ID),
    }
    lines = _card_price_lines(prices, RATES)
    in_line = next(line for line in lines if "Rs" in line)
    assert in_line.startswith("🇮🇳 <b><a href=")
    assert "</b>" in in_line
    bold_end = in_line.index("</b>")
    assert in_line.find("</a>") <= bold_end + len("</b>") + 1


def test_card_price_lines_no_old_price():
    prices = {"en-us": RegionPrice(9.99, "$", None, None, ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES, old_prices=None)
    assert "↓" not in lines[0]
    assert "↑" not in lines[0]


def test_card_price_lines_price_drop_arrow():
    prices = {"en-gb": RegionPrice(39.99, "€", None, None, ps_id=EP_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-gb": 59.99})
    assert "↓" in lines[0]
    assert "<s>" in lines[0]


def test_card_price_lines_price_increase_arrow():
    prices = {"en-gb": RegionPrice(69.99, "€", None, None, ps_id=EP_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-gb": 59.99})
    assert "↑" in lines[0]
    assert "<s>" in lines[0]


def test_card_price_lines_no_arrow_when_price_unchanged():
    prices = {"en-gb": RegionPrice(59.99, "€", None, None, ps_id=EP_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-gb": 59.99})
    assert "↓" not in lines[0]
    assert "↑" not in lines[0]


def test_card_price_lines_old_usd_shown():
    prices = {"en-gb": RegionPrice(39.99, "€", None, None, ps_id=EP_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-gb": 59.99})
    assert "($" in lines[0]


def test_card_price_lines_no_old_usd_for_usd():
    prices = {"en-us": RegionPrice(7.99, "$", None, None, ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-us": 9.99})
    assert "↓" in lines[0]
    old_part = lines[0].split("↓")[1]
    assert "($" not in old_part


def test_card_price_lines_no_arrow_when_sale_and_old_equals_base():
    # base_price == old_price → strikethrough base already visible, arrow would duplicate
    prices = {"en-us": RegionPrice(39.99, "$", 59.99, "-33%", ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-us": 59.99})
    assert "↓" not in lines[0]


def test_card_price_lines_arrow_when_sale_and_old_differs_from_base():
    # base_price != old_price → price dropped from an intermediate value, show arrow
    prices = {"en-us": RegionPrice(39.99, "$", 59.99, "-33%", ps_id=PS_ID)}
    lines = _card_price_lines(prices, RATES, old_prices={"en-us": 49.99})
    assert "↓" in lines[0]


# --- format_game_list ---

def test_format_game_list_empty():
    result = format_game_list("Title", "Footer", [], {})
    assert result == "Nothing found. Try a different query."


def test_format_game_list_structure():
    result = format_game_list("My Games", "The end", [GAME], [{"en-us": RegionPrice(9.99, "$", None, None)}], RATES)
    assert result.startswith("My Games")
    assert result.endswith("The end")
    assert "Test Game" in result


def test_format_game_list_no_prices():
    result = format_game_list("Title", "Footer", [GAME], [{}], RATES)
    assert "Test Game" in result


# --- format_game_card ---

def test_format_game_card_structure():
    prices = {"en-in": RegionPrice(4999.0, "Rs", None, None)}
    result = format_game_card(GAME, prices, RATES, title="Details:", footer="Add region in /settings")
    assert result.startswith("Details:")
    assert result.endswith("Add region in /settings")
    assert "Test Game" in result
    assert "Prices by region:" in result


def test_format_game_card_no_prices_no_header():
    result = format_game_card(GAME, {}, RATES)
    assert "Prices by region:" not in result


def test_format_game_card_with_old_prices():
    prices = {"en-in": RegionPrice(3999.0, "Rs", None, None)}
    result = format_game_card(GAME, prices, RATES, old_prices={"en-in": 4999.0})
    assert "↓" in result
    assert "<s>" in result


# --- _offer_end_line ---

def test_offer_end_line_shown_when_discounted():
    end = datetime(2026, 5, 22, 22, 59, tzinfo=timezone.utc)
    prices = {"en-us": RegionPrice(19.99, "$", 39.99, "-50%", discount_end=end)}
    line = _offer_end_line(prices)
    assert line == "22 May 2026 22:59 UTC"


def test_offer_end_line_date_only_fallback():
    prices = {"en-us": RegionPrice(19.99, "$", 39.99, "-50%", discount_end=datetime(2026, 5, 22, tzinfo=timezone.utc))}
    line = _offer_end_line(prices)
    assert line == "22 May 2026"


def test_format_offer_end_with_time():
    end = datetime(2026, 7, 16, 6, 59, tzinfo=timezone.utc)
    assert _format_offer_end(end) == "16 Jul 2026 06:59 UTC"


def test_format_offer_end_date_only():
    end = datetime(2026, 7, 16, tzinfo=timezone.utc)
    assert _format_offer_end(end) == "16 Jul 2026"


def test_format_game_card_offer_end_date_only_bold():
    end = datetime(2026, 7, 16, tzinfo=timezone.utc)
    prices = {"en-us": RegionPrice(37.49, "$", 49.99, "-25%", discount_end=end)}
    result = format_game_card(GAME, prices, RATES)
    assert "Offer ends <b>16 Jul 2026</b>" in result
    assert "UTC" not in result.split("Offer ends")[1].split("\n")[0]


def test_offer_end_line_none_when_no_discount():
    end = datetime(2026, 5, 22, 22, 59, tzinfo=timezone.utc)
    prices = {"en-us": RegionPrice(39.99, "$", None, None, discount_end=end)}
    line = _offer_end_line(prices)
    assert line is None


def test_offer_end_line_none_when_no_end_date():
    prices = {"en-us": RegionPrice(19.99, "$", 39.99, "-50%", discount_end=None)}
    line = _offer_end_line(prices)
    assert line is None


def test_offer_end_takes_first_discounted_region():
    end_us = datetime(2026, 5, 22, 22, 59, tzinfo=timezone.utc)
    end_gb = datetime(2026, 5, 30, 22, 59, tzinfo=timezone.utc)
    prices = {
        "en-us": RegionPrice(19.99, "$", None, None, discount_end=end_us),
        "en-gb": RegionPrice(14.99, "£", 29.99, "-50%", discount_end=end_gb),
    }
    line = _offer_end_line(prices)
    assert line == "30 May 2026 22:59 UTC"


def test_format_game_card_shows_offer_end():
    end = datetime(2026, 5, 22, 22, 59, tzinfo=timezone.utc)
    prices = {"en-us": RegionPrice(19.99, "$", 39.99, "-50%", discount_end=end)}
    result = format_game_card(GAME, prices, RATES)
    assert "Offer ends <b>22 May 2026 22:59 UTC</b>" in result


# --- N/A price line ---


def test_card_price_lines_shows_na_when_price_is_none():
    prices = {"en-us": RegionPrice(price=None, currency=None, base_price=None, discount_text=None)}
    lines = _card_price_lines(prices, {})
    assert len(lines) == 1
    assert "N/A" in lines[0]


def test_format_game_card_no_offer_end_without_discount():
    prices = {"en-us": RegionPrice(39.99, "$", None, None)}
    result = format_game_card(GAME, prices, RATES)
    assert "Offer ends" not in result


# --- past sales ---

def test_format_past_sales_with_sales():
    from bot.formatters import format_past_sales_lines
    from services.price_history import RegionSaleHistory, UserGameSaleHistory

    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 1, 12, tzinfo=timezone.utc),
        regions=[
            RegionSaleHistory(
                "tr-tr",
                "TL",
                [(174.90, datetime(2026, 5, 18, tzinfo=timezone.utc))],
            )
        ],
        total_sales=1,
    )
    lines = format_past_sales_lines(history, "duration", limit_per_region=3)
    text = "\n".join(lines)
    assert "Past sales" in text
    assert "174" in text
    assert "<i>Tracking since" in text


def test_format_game_card_includes_past_sales():
    from services.price_history import RegionSaleHistory, UserGameSaleHistory

    prices = {"tr-tr": RegionPrice(174.90, "TL", 1749.0, "-90%")}
    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 1, 12, tzinfo=timezone.utc),
        regions=[
            RegionSaleHistory(
                "tr-tr",
                "TL",
                [(174.90, datetime(2026, 5, 18, tzinfo=timezone.utc))],
            )
        ],
        total_sales=1,
    )
    result = format_game_card(GAME, prices, RATES, sale_history=history, history_format="duration")
    assert "Past sales" in result
    assert "174" in result


def test_format_game_card_offer_end_before_past_sales():
    from services.price_history import RegionSaleHistory, UserGameSaleHistory

    end = datetime(2026, 5, 28, 6, 59, tzinfo=timezone.utc)
    prices = {"tr-tr": RegionPrice(174.90, "TL", 1749.0, "-90%", discount_end=end)}
    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 5, 23, tzinfo=timezone.utc),
        regions=[
            RegionSaleHistory(
                "tr-tr",
                "TL",
                [(174.90, datetime(2026, 5, 18, tzinfo=timezone.utc))],
            )
        ],
        total_sales=1,
    )
    result = format_game_card(
        GAME, prices, RATES, sale_history=history, history_format="duration",
    )
    assert result.index("Offer ends <b>") < result.index("Past sales")
    assert result.index("Past sales") < result.index("<i>Tracking since")


def test_format_game_card_save_compatibility_after_past_sales():
    from services.price_history import RegionSaleHistory, UserGameSaleHistory

    end = datetime(2026, 5, 28, 6, 59, tzinfo=timezone.utc)
    prices = {
        "en-us": RegionPrice(19.99, "$", 39.99, "-50%", ps_id=US_CONTROL, discount_end=end),
        "en-br": RegionPrice(99.0, "R$", 199.0, "-50%", ps_id=BR_CONTROL, discount_end=end),
    }
    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 5, 23, tzinfo=timezone.utc),
        regions=[
            RegionSaleHistory(
                "en-us",
                "$",
                [(19.99, datetime(2026, 5, 18, tzinfo=timezone.utc))],
            )
        ],
        total_sales=1,
    )
    result = format_game_card(
        GAME, prices, RATES, sale_history=history, history_format="duration",
        show_cross_region_saves=True,
    )
    assert result.index("All regions share saves") < result.index("Offer ends")
    assert result.index("Offer ends") < result.index("Past sales")
    assert result.index("Past sales") < result.index("<i>Tracking since")


def test_format_game_card_shows_tracking_without_past_sales():
    from services.price_history import UserGameSaleHistory

    prices = {"en-us": RegionPrice(37.49, "$", 49.99, "-25%")}
    history = UserGameSaleHistory(
        tracking_since=datetime(2026, 7, 4, tzinfo=timezone.utc),
        regions=[],
        total_sales=0,
    )
    result = format_game_card(GAME, prices, RATES, sale_history=history)
    assert "Past sales" not in result
    assert "<i>Tracking since 04 Jul 2026</i>" in result


# --- save compatibility ---


def test_save_compatibility_hidden_for_single_region():
    prices = {"en-us": RegionPrice(9.99, "$", None, None, ps_id=US_CONTROL)}
    assert _format_save_compatibility_line(prices) is None


def test_save_compatibility_all_regions_share_saves():
    prices = {
        "en-us": RegionPrice(29.99, "$", None, None, ps_id=US_CONTROL),
        "en-br": RegionPrice(149.0, "R$", None, None, ps_id=BR_CONTROL),
    }
    assert _format_save_compatibility_line(prices) == "All regions share saves"


def test_save_compatibility_multiple_groups():
    prices = {
        "en-us": RegionPrice(29.99, "$", None, None, ps_id=US_CONTROL),
        "en-br": RegionPrice(149.0, "R$", None, None, ps_id=BR_CONTROL),
        "tr-tr": RegionPrice(899.0, "TL", None, None, ps_id=TR_CONTROL),
    }
    line = _format_save_compatibility_line(prices)
    assert line == (
        "Save compatible regions:\n"
        f"• {locale_flag('en-us')} {locale_flag('en-br')}\n"
        f"• {locale_flag('tr-tr')}"
    )
    assert "🟢" not in line
    assert "🔵" not in line


def test_save_compatibility_skips_unparseable_ps_id():
    prices = {
        "en-us": RegionPrice(29.99, "$", None, None, ps_id=US_CONTROL),
        "en-gb": RegionPrice(29.99, "£", None, None, ps_id="NODASH"),
    }
    assert _format_save_compatibility_line(prices) is None


def test_format_game_card_shows_save_compatibility():
    prices = {
        "en-us": RegionPrice(29.99, "$", None, None, ps_id=US_CONTROL),
        "en-br": RegionPrice(149.0, "R$", None, None, ps_id=BR_CONTROL),
    }
    result = format_game_card(GAME, prices, RATES, show_cross_region_saves=True)
    assert result.index("Prices by region:") < result.index("All regions share saves")


def test_format_game_card_hides_save_compatibility_when_disabled():
    prices = {
        "en-us": RegionPrice(29.99, "$", None, None, ps_id=US_CONTROL),
        "en-br": RegionPrice(149.0, "R$", None, None, ps_id=BR_CONTROL),
    }
    result = format_game_card(GAME, prices, RATES, show_cross_region_saves=False)
    assert "All regions share saves" not in result
    assert "Save compatible" not in result


def test_format_game_card_save_compatibility_before_offer_end():
    end = datetime(2026, 5, 22, 22, 59, tzinfo=timezone.utc)
    prices = {
        "en-us": RegionPrice(19.99, "$", 39.99, "-50%", ps_id=US_CONTROL, discount_end=end),
        "en-br": RegionPrice(99.0, "R$", 199.0, "-50%", ps_id=BR_CONTROL, discount_end=end),
    }
    result = format_game_card(GAME, prices, RATES, show_cross_region_saves=True)
    assert result.index("All regions share saves") < result.index("Offer ends")
