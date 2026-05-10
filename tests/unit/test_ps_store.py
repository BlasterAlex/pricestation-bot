import json

import pytest

from services.ps_store import search_games

FAKE_APOLLO = {
    "ROOT_QUERY": {
        'universalSearch({"countryCode":"US","languageCode":"en","nextCursor":"","pageOffset":0,"pageSize":24,"searchTerm":"spider+man"})': {  # noqa: E501
            "__typename": "UniversalSearchResponse",
            "searchTerm": "spider+man",
            "next": "",
            "pageInfo": {"__typename": "PageInfo", "totalCount": 3, "offset": 0, "size": 24, "isLast": True},
            "results": [
                {"__ref": "Product:UP9000-PPSA03016_00-MARVELSPIDERMAN2:en-us"},
                {"__ref": "Product:UP9000-PPSA03016_00-MSM2TU1000000000:en-us"},  # COSTUME — filtered
                {"__ref": "Product:UP9000-PPSA01467_00-MARVELSSPIDERMAN:en-us"},
            ],
        }
    },
    "Product:UP9000-PPSA03016_00-MARVELSPIDERMAN2:en-us": {
        "__typename": "Product",
        "id": "UP9000-PPSA03016_00-MARVELSPIDERMAN2",
        "name": "Marvel's Spider-Man 2",
        "platforms": ["PS5"],
        "storeDisplayClassification": "FULL_GAME",
        "price": {"__typename": "SkuPrice", "basePrice": "$69.99", "discountedPrice": "$69.99"},
        "media": [{"__typename": "Media", "role": "MASTER", "type": "IMAGE", "url": "https://example.com/cover.png"}],
    },
    "Product:UP9000-PPSA03016_00-MSM2TU1000000000:en-us": {
        "__typename": "Product",
        "id": "UP9000-PPSA03016_00-MSM2TU1000000000",
        "name": "Marvel's Spider-Man 2 Fly N Fresh Suit Pack",
        "platforms": ["PS5"],
        "storeDisplayClassification": "COSTUME",
        "price": {"__typename": "SkuPrice", "basePrice": "Free", "discountedPrice": "Free"},
        "media": [],
    },
    "Product:UP9000-PPSA01467_00-MARVELSSPIDERMAN:en-us": {
        "__typename": "Product",
        "id": "UP9000-PPSA01467_00-MARVELSSPIDERMAN",
        "name": "Marvel's Spider-Man Remastered",
        "platforms": ["PS5"],
        "storeDisplayClassification": "FULL_GAME",
        "price": {"__typename": "SkuPrice", "basePrice": "$49.99", "discountedPrice": "$49.99"},
        "media": [],
    },
}

FAKE_HTML = f"""
<html><head>
<script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"apolloState": FAKE_APOLLO}})}</script>
</head><body></body></html>
"""


@pytest.fixture
def mock_store(mocker):
    mock_resp = mocker.AsyncMock()
    mock_resp.raise_for_status = mocker.Mock()
    mock_resp.text = mocker.AsyncMock(return_value=FAKE_HTML)
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
    types = {r["type"] for r in results}
    assert types <= {"FULL_GAME", "PREMIUM_EDITION", "GAME_BUNDLE"}


@pytest.mark.asyncio
async def test_search_filters_non_games(mock_store):
    results = await search_games("spider man")
    ids = [r["ps_id"] for r in results]
    assert "UP9000-PPSA03016_00-MSM2TU1000000000" not in ids


@pytest.mark.asyncio
async def test_search_result_fields(mock_store):
    results = await search_games("spider man")
    game = next(r for r in results if r["ps_id"] == "UP9000-PPSA03016_00-MARVELSPIDERMAN2")
    assert game["title"] == "Marvel's Spider-Man 2"
    assert game["platforms"] == ["PS5"]
    assert game["price"] == 69.99
    assert game["currency"] == "$"
    assert game["base_price"] is None
    assert game["discount_text"] is None
    assert game["cover_url"] == "https://example.com/cover.png"


@pytest.mark.asyncio
async def test_search_discount_fields(mock_store):
    from services.ps_store import _resolve_product
    apollo = {
        **FAKE_APOLLO,
        "Product:SALE_GAME:en-us": {
            "__typename": "Product",
            "id": "SALE_GAME",
            "name": "Sale Game",
            "platforms": ["PS4"],
            "storeDisplayClassification": "FULL_GAME",
            "price": {
                "__typename": "SkuPrice",
                "basePrice": "$39.99",
                "discountedPrice": "$19.99",
                "discountText": "-50%",
            },
            "media": [],
        },
    }
    product = _resolve_product(apollo, "Product:SALE_GAME:en-us")
    assert product["price"] == 19.99
    assert product["base_price"] == 39.99
    assert product["discount_text"] == "-50%"


@pytest.mark.asyncio
async def test_search_no_cover_url(mock_store):
    results = await search_games("spider man")
    game = next(r for r in results if r["ps_id"] == "UP9000-PPSA01467_00-MARVELSSPIDERMAN")
    assert game["cover_url"] is None


@pytest.mark.asyncio
async def test_search_free_price_is_none(mock_store):
    # COSTUME отфильтрован, но проверяем что Free → None через прямой вызов _resolve_product
    from services.ps_store import _resolve_product
    apollo = FAKE_APOLLO
    product = _resolve_product(apollo, "Product:UP9000-PPSA03016_00-MSM2TU1000000000:en-us")
    assert product["price"] is None
    assert product["currency"] is None
