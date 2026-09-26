import json
from urllib.parse import parse_qs, urlparse

import pytest

from clients import ps_store

CONCEPT_ID = "10001130"
DEFAULT_PRODUCT_ID = "UP9000-PPSA08338_00-STANDARD00000000"


def _concept_payload(default_product_id=DEFAULT_PRODUCT_ID):
    concept = None
    if default_product_id is not None:
        concept = {"defaultProduct": {"id": default_product_id}}
    return {"data": {"conceptRetrieve": concept}}


def _product(
    ps_id: str,
    classification: str = "FULL_GAME",
    *,
    is_free: bool = False,
    upsell_service: str = "NONE",
):
    return {
        "id": ps_id,
        "name": f"{classification} edition",
        "platforms": ["PS5"],
        "storeDisplayClassification": classification,
        "media": [{"role": "MASTER", "type": "IMAGE", "url": "https://example.com/cover.png"}],
        "webctas": [{
            "type": "ADD_TO_CART",
            "meta": {"upSellService": upsell_service},
            "price": {
                "isFree": is_free,
                "basePriceValue": 7999,
                "discountedValue": 5999,
                "currencyCode": "EUR",
                "discountText": "-25%",
            },
        }],
    }


def _editions_payload(products):
    return {"data": {"productRetrieve": {"concept": {"products": products}}}}


@pytest.fixture
def make_mock_store(mocker):
    def _factory(*payloads):
        sessions = []
        for payload in payloads:
            response = mocker.AsyncMock()
            response.status = 200
            response.json = mocker.AsyncMock(return_value=payload)
            response.__aenter__ = mocker.AsyncMock(return_value=response)
            response.__aexit__ = mocker.AsyncMock(return_value=False)

            session = mocker.AsyncMock()
            session.get = mocker.Mock(return_value=response)
            session.__aenter__ = mocker.AsyncMock(return_value=session)
            session.__aexit__ = mocker.AsyncMock(return_value=False)
            sessions.append(session)

        mocker.patch("clients.ps_store.aiohttp.ClientSession", side_effect=sessions)
        return sessions

    return _factory


@pytest.mark.asyncio
async def test_get_concept_default_product_id(make_mock_store):
    sessions = make_mock_store(_concept_payload())

    result = await ps_store.get_concept_default_product_id(CONCEPT_ID, "en-us")

    assert result == DEFAULT_PRODUCT_ID
    url = sessions[0].get.call_args.args[0]
    query = parse_qs(urlparse(url).query)
    assert query["operationName"] == ["metGetConceptById"]
    assert json.loads(query["variables"][0]) == {"conceptId": CONCEPT_ID}
    assert sessions[0].get.call_args.kwargs["headers"]["Referer"] == (
        f"https://store.playstation.com/en-us/concept/{CONCEPT_ID}"
    )


@pytest.mark.asyncio
async def test_list_concept_editions_returns_empty_when_concept_missing(make_mock_store):
    make_mock_store(_concept_payload(None))

    assert await ps_store.list_concept_editions(CONCEPT_ID) == []


@pytest.mark.asyncio
async def test_list_concept_editions_returns_one_paid_full_game(make_mock_store):
    sessions = make_mock_store(
        _concept_payload(),
        _editions_payload([_product(DEFAULT_PRODUCT_ID)]),
    )

    results = await ps_store.list_concept_editions(CONCEPT_ID)

    assert len(results) == 1
    game, price = results[0]
    assert game.title == "FULL_GAME edition"
    assert price.ps_id == DEFAULT_PRODUCT_ID
    assert price.price == 59.99
    assert price.base_price == 79.99
    assert price.currency == "€"
    url = sessions[1].get.call_args.args[0]
    query = parse_qs(urlparse(url).query)
    assert query["operationName"] == ["productRetrieveForUpsellWithCtas"]
    assert json.loads(query["variables"][0]) == {"productId": DEFAULT_PRODUCT_ID}


@pytest.mark.asyncio
async def test_get_concept_default_product_id_raises_on_http_error(
    make_mock_store,
):
    sessions = make_mock_store(_concept_payload())
    sessions[0].get.return_value.status = 503

    with pytest.raises(ps_store.PSStoreAPIError):
        await ps_store.get_concept_default_product_id(CONCEPT_ID)


@pytest.mark.asyncio
async def test_list_concept_editions_raises_on_http_error(make_mock_store):
    sessions = make_mock_store(_concept_payload(), _editions_payload([]))
    sessions[1].get.return_value.status = 503

    with pytest.raises(ps_store.PSStoreAPIError):
        await ps_store.list_concept_editions(CONCEPT_ID)


@pytest.mark.asyncio
async def test_list_concept_editions_returns_full_game_and_bundle(make_mock_store):
    bundle_id = "UP9000-PPSA08338_00-DELUXE0000000000"
    make_mock_store(
        _concept_payload(),
        _editions_payload([
            _product(DEFAULT_PRODUCT_ID),
            _product(bundle_id, "GAME_BUNDLE"),
        ]),
    )

    results = await ps_store.list_concept_editions(CONCEPT_ID)

    assert [game.type for game, _ in results] == ["FULL_GAME", "GAME_BUNDLE"]
    assert [price.ps_id for _, price in results] == [DEFAULT_PRODUCT_ID, bundle_id]


@pytest.mark.asyncio
async def test_list_concept_editions_filters_demo_and_free_only(make_mock_store):
    make_mock_store(
        _concept_payload(),
        _editions_payload([
            _product("UP9000-DEMO", "DEMO"),
            _product("UP9000-FREE", is_free=True),
            _product("UP9000-PLUS", upsell_service="PS_PLUS"),
        ]),
    )

    assert await ps_store.list_concept_editions(CONCEPT_ID) == []
