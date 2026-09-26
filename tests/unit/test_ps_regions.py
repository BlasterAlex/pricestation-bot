import pytest

from clients import ps_regions


@pytest.fixture(autouse=True)
def _clear_regions_cache():
    ps_regions._cache = None
    ps_regions._cache_at = 0.0
    yield
    ps_regions._cache = None
    ps_regions._cache_at = 0.0


@pytest.mark.asyncio
async def test_get_ps_regions_strips_name_and_locale(mocker):
    payload = {
        "regions": [
            {
                "countries": [
                    {"countryName": "India ", "localeCode": " en-in "},
                    {"countryName": "United States", "localeCode": "en-us"},
                ]
            }
        ]
    }
    response = mocker.AsyncMock()
    response.raise_for_status = mocker.Mock()
    response.json = mocker.AsyncMock(return_value=payload)
    response.__aenter__ = mocker.AsyncMock(return_value=response)
    response.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.AsyncMock()
    session.get = mocker.Mock(return_value=response)
    session.__aenter__ = mocker.AsyncMock(return_value=session)
    session.__aexit__ = mocker.AsyncMock(return_value=False)
    mocker.patch("clients.ps_regions.aiohttp.ClientSession", return_value=session)

    countries = await ps_regions.get_ps_regions()

    assert countries == [
        {"name": "India", "locale": "en-in"},
        {"name": "United States", "locale": "en-us"},
    ]
