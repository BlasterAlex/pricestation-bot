import pytest

from services.ps_store import GameInfo, RegionPrice

SEED_PS_ID = "UP0001-PPSA00001_00-TESTGAME00000000"
EU_PS_ID = "EP0001-PPSA00001_00-TESTGAME00000000"


def _game(
    title: str = "Test Game",
    *,
    ps_id_suffix: str | None = "TESTGAME00000000",
) -> GameInfo:
    return GameInfo(
        title=title,
        platforms=["PS5"],
        type="FULL_GAME",
        cover_url=None,
        ps_id_suffix=ps_id_suffix,
    )


def _price(ps_id: str, price: float, currency: str) -> RegionPrice:
    return RegionPrice(
        price=price,
        currency=currency,
        base_price=None,
        discount_text=None,
        ps_id=ps_id,
    )


@pytest.mark.asyncio
async def test_uses_seed_id_for_seed_locale_and_remapped_id_for_second_region(mocker):
    from services import ps_link_prices

    seed_game = _game()
    us_price = _price(SEED_PS_ID, 59.99, "$")
    eu_price = _price(EU_PS_ID, 49.99, "€")
    get_game_info = mocker.patch(
        "services.ps_link_prices.get_game_info",
        side_effect=[(seed_game, us_price), (seed_game, eu_price)],
    )
    search_games = mocker.patch("services.ps_link_prices.search_games")

    result = await ps_link_prices.prices_for_tracked_regions(
        seed_game,
        SEED_PS_ID,
        "en-us",
        ["en-us", "en-gb"],
    )

    assert result == {"en-us": us_price, "en-gb": eu_price}
    assert get_game_info.await_args_list == [
        mocker.call(SEED_PS_ID, "en-us"),
        mocker.call(EU_PS_ID, "en-gb"),
    ]
    search_games.assert_not_awaited()


@pytest.mark.asyncio
async def test_remap_miss_uses_first_search_suffix_match(mocker):
    from services import ps_link_prices

    seed_game = _game()
    other_game = _game("Other Game", ps_id_suffix="OTHER")
    localized_game = _game("Localized Test Game")
    matching_price = _price(EU_PS_ID, 49.99, "€")
    mocker.patch(
        "services.ps_link_prices.get_game_info",
        return_value=None,
    )
    search_games = mocker.patch(
        "services.ps_link_prices.search_games",
        return_value=[
            (other_game, _price("EP0001-OTHER", 39.99, "€")),
            (localized_game, matching_price),
        ],
    )

    result = await ps_link_prices.prices_for_tracked_regions(
        seed_game,
        SEED_PS_ID,
        "en-us",
        ["en-gb"],
    )

    assert result == {"en-gb": matching_price}
    search_games.assert_awaited_once_with("Test Game", "en-gb")


@pytest.mark.asyncio
async def test_omits_region_when_remap_and_search_both_miss(mocker):
    from services import ps_link_prices

    seed_game = _game()
    mocker.patch("services.ps_link_prices.get_game_info", return_value=None)
    mocker.patch(
        "services.ps_link_prices.search_games",
        return_value=[(_game("Other Game", ps_id_suffix="OTHER"), _price("EP-OTHER", 1, "€"))],
    )

    result = await ps_link_prices.prices_for_tracked_regions(
        seed_game,
        SEED_PS_ID,
        "en-us",
        ["en-gb"],
    )

    assert result == {}


@pytest.mark.asyncio
async def test_omits_failed_region_and_keeps_successful_region(mocker):
    from services import ps_link_prices

    seed_game = _game()
    us_price = _price(SEED_PS_ID, 59.99, "$")
    mocker.patch(
        "services.ps_link_prices._price_for_region",
        side_effect=[
            ("en-us", us_price),
            RuntimeError("temporary regional failure"),
        ],
    )

    result = await ps_link_prices.prices_for_tracked_regions(
        seed_game,
        SEED_PS_ID,
        "en-us",
        ["en-us", "en-gb"],
    )

    assert result == {"en-us": us_price}
