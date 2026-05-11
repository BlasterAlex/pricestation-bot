import pytest

from services.ps_store import GameResult, get_game_info, search_games

FAKE_GQL_SEARCH = {
    "data": {
        "universalSearch": {
            "next": "",
            "pageInfo": {"totalCount": 3, "offset": 0, "size": 3, "isLast": True},
            "results": [
                {
                    "__typename": "Product",
                    "id": "UP9000-PPSA03016_00-MARVELSPIDERMAN2",
                    "name": "Marvel's Spider-Man 2",
                    "platforms": ["PS5"],
                    "storeDisplayClassification": "FULL_GAME",
                    "price": {
                        "basePrice": "$69.99",
                        "discountedPrice": "$69.99",
                        "discountText": None,
                        "isFree": False,
                    },
                    "media": [{"role": "MASTER", "type": "IMAGE", "url": "https://example.com/cover.png"}],
                },
                {
                    "__typename": "Product",
                    "id": "UP9000-PPSA03016_00-MSM2TU1000000000",
                    "name": "Marvel's Spider-Man 2 Fly N Fresh Suit Pack",
                    "platforms": ["PS5"],
                    "storeDisplayClassification": "COSTUME",
                    "price": {"basePrice": "Free", "discountedPrice": "Free", "discountText": None, "isFree": True},
                    "media": [],
                },
                {
                    "__typename": "Product",
                    "id": "UP9000-PPSA01467_00-MARVELSSPIDERMAN",
                    "name": "Marvel's Spider-Man Remastered",
                    "platforms": ["PS5"],
                    "storeDisplayClassification": "FULL_GAME",
                    "price": {
                        "basePrice": "$49.99",
                        "discountedPrice": "$49.99",
                        "discountText": None,
                        "isFree": False,
                    },
                    "media": [],
                },
            ],
        }
    }
}


@pytest.fixture
def mock_store(mocker):
    mock_resp = mocker.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value=FAKE_GQL_SEARCH)
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)

    mocker.patch("services.ps_store.aiohttp.ClientSession", return_value=mock_session)


@pytest.mark.asyncio
async def test_search_returns_only_games(mock_store):
    results = await search_games("spider man")
    types = {r.type for r in results}
    assert types <= {"FULL_GAME", "PREMIUM_EDITION", "GAME_BUNDLE"}


@pytest.mark.asyncio
async def test_search_filters_non_games(mock_store):
    results = await search_games("spider man")
    ids = [r.ps_id for r in results]
    assert "UP9000-PPSA03016_00-MSM2TU1000000000" not in ids


@pytest.mark.asyncio
async def test_search_result_fields(mock_store):
    results = await search_games("spider man")
    game = next(r for r in results if r.ps_id == "UP9000-PPSA03016_00-MARVELSPIDERMAN2")
    assert isinstance(game, GameResult)
    assert game.title == "Marvel's Spider-Man 2"
    assert game.platforms == ["PS5"]
    assert game.price == 69.99
    assert game.currency == "$"
    assert game.base_price is None
    assert game.discount_text is None
    assert game.cover_url == "https://example.com/cover.png"


@pytest.mark.asyncio
async def test_search_discount_fields(mocker):
    fake = {
        "data": {
            "universalSearch": {
                "next": "",
                "pageInfo": {"totalCount": 1, "offset": 0, "size": 1, "isLast": True},
                "results": [
                    {
                        "__typename": "Product",
                        "id": "SALE_GAME",
                        "name": "Sale Game",
                        "platforms": ["PS4"],
                        "storeDisplayClassification": "FULL_GAME",
                        "price": {
                            "basePrice": "$39.99",
                            "discountedPrice": "$19.99",
                            "discountText": "-50%",
                            "isFree": False,
                        },
                        "media": [],
                    }
                ],
            }
        }
    }
    mock_resp = mocker.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value=fake)
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
    mocker.patch("services.ps_store.aiohttp.ClientSession", return_value=mock_session)

    results = await search_games("sale game")
    assert len(results) == 1
    assert results[0].price == 19.99
    assert results[0].base_price == 39.99
    assert results[0].discount_text == "-50%"


@pytest.mark.asyncio
async def test_search_no_cover_url(mock_store):
    results = await search_games("spider man")
    game = next(r for r in results if r.ps_id == "UP9000-PPSA01467_00-MARVELSSPIDERMAN")
    assert game.cover_url is None


@pytest.mark.asyncio
async def test_search_free_price_is_none(mock_store):
    fake = {
        "data": {
            "universalSearch": {
                "next": "",
                "pageInfo": {"totalCount": 1, "offset": 0, "size": 1, "isLast": True},
                "results": [
                    {
                        "__typename": "Product",
                        "id": "FREE_GAME",
                        "name": "Free Game Spider Man",
                        "platforms": ["PS5"],
                        "storeDisplayClassification": "FULL_GAME",
                        "price": {"basePrice": "Free", "discountedPrice": "Free", "discountText": None, "isFree": True},
                        "media": [],
                    }
                ],
            }
        }
    }
    # reuse mock_store pattern inline to avoid fixture conflict
    import unittest.mock as m

    import services.ps_store as mod
    mock_resp = m.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = m.AsyncMock(return_value=fake)
    mock_resp.__aenter__ = m.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = m.AsyncMock(return_value=False)
    mock_session = m.AsyncMock()
    mock_session.get = m.Mock(return_value=mock_resp)
    mock_session.__aenter__ = m.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = m.AsyncMock(return_value=False)
    with m.patch.object(mod.aiohttp, "ClientSession", return_value=mock_session):
        results = await search_games("spider man")
    assert results[0].price is None
    assert results[0].currency is None


@pytest.mark.asyncio
async def test_search_ps_plus_free_falls_back_to_base_price(mocker):
    fake = {
        "data": {
            "universalSearch": {
                "next": "",
                "pageInfo": {"totalCount": 1, "offset": 0, "size": 1, "isLast": True},
                "results": [
                    {
                        "__typename": "Product",
                        "id": "PS_PLUS_GAME",
                        "name": "Spider Man Game",
                        "platforms": ["PS5"],
                        "storeDisplayClassification": "FULL_GAME",
                        "price": {
                            "basePrice": "$19.99",
                            "discountedPrice": "Free",
                            "discountText": None,
                            "isFree": True,
                        },
                        "media": [],
                    }
                ],
            }
        }
    }
    mock_resp = mocker.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value=fake)
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
    mocker.patch("services.ps_store.aiohttp.ClientSession", return_value=mock_session)

    results = await search_games("spider man")
    assert len(results) == 1
    assert results[0].price == 19.99
    assert results[0].currency == "$"
    assert results[0].base_price is None


# --- get_game_info tests ---

GAME_INFO_PS_ID = "EP9000-PPSA08338_00-MARVELSPIDERMAN2"

GAME_INFO_GQL = {
    "data": {
        "productRetrieve": {
            "__typename": "Product",
            "id": GAME_INFO_PS_ID,
            "topCategory": "GAME",
            "concept": {
                "__typename": "Concept",
                "products": [
                    {
                        "__typename": "Product",
                        "id": GAME_INFO_PS_ID,
                        "name": "Marvel's Spider-Man 2",
                        "platforms": ["PS5"],
                        "storeDisplayClassification": "FULL_GAME",
                        "media": [
                            {"__typename": "Media", "role": "MASTER", "type": "IMAGE",
                             "url": "https://example.com/ep_cover.png"},
                        ],
                        "webctas": [
                            {
                                "__typename": "GameCTA",
                                "type": "ADD_TO_CART",
                                "meta": {"__typename": "CTAMeta", "upSellService": "NONE"},
                                "price": {
                                    "__typename": "Price",
                                    "isFree": False,
                                    "basePriceValue": 7999,
                                    "discountedValue": 5999,
                                    "currencyCode": "EUR",
                                    "discountText": "-25%",
                                },
                            }
                        ],
                    }
                ],
            },
        }
    }
}


@pytest.fixture
def mock_game_info(mocker):
    mock_resp = mocker.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value=GAME_INFO_GQL)
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)

    mocker.patch("services.ps_store.aiohttp.ClientSession", return_value=mock_session)


@pytest.mark.asyncio
async def test_get_game_info_returns_game(mock_game_info):
    result = await get_game_info(GAME_INFO_PS_ID)
    assert isinstance(result, GameResult)
    assert result.ps_id == GAME_INFO_PS_ID
    assert result.title == "Marvel's Spider-Man 2"
    assert result.platforms == ["PS5"]
    assert result.type == "FULL_GAME"


@pytest.mark.asyncio
async def test_get_game_info_price_fields(mock_game_info):
    result = await get_game_info(GAME_INFO_PS_ID)
    assert result.price == 59.99
    assert result.base_price == 79.99
    assert result.currency == "€"
    assert result.discount_text == "-25%"


@pytest.mark.asyncio
async def test_get_game_info_cover_url(mock_game_info):
    result = await get_game_info(GAME_INFO_PS_ID)
    assert result.cover_url == "https://example.com/ep_cover.png"


@pytest.mark.asyncio
async def test_get_game_info_not_found_returns_none(mocker):
    mock_resp = mocker.AsyncMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value={"data": {"productRetrieve": None}})
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)

    mocker.patch("services.ps_store.aiohttp.ClientSession", return_value=mock_session)

    result = await get_game_info(GAME_INFO_PS_ID)
    assert result is None
