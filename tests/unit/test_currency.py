import time
from unittest.mock import AsyncMock

import pytest

import services.currency as _mod
from services.currency import _fetch_rates, get_rates, to_usd


@pytest.fixture(autouse=True)
def _reset_cache():
    _mod._RATES_CACHE = {}
    _mod._cache_ts = 0.0
    yield
    _mod._RATES_CACHE = {}
    _mod._cache_ts = 0.0


def _mock_http(mocker, status: int, payload: dict | None = None):
    mock_resp = mocker.AsyncMock()
    mock_resp.status = status
    if payload is not None:
        mock_resp.json = mocker.AsyncMock(return_value=payload)
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_session = mocker.AsyncMock()
    mock_session.get = mocker.Mock(return_value=mock_resp)
    mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
    mocker.patch("services.currency.aiohttp.ClientSession", return_value=mock_session)


# ── _fetch_rates ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_rates_returns_rates_on_200(mocker):
    _mock_http(mocker, 200, {"rates": {"EUR": 0.92, "GBP": 0.79}})
    rates = await _fetch_rates()
    assert rates == {"EUR": 0.92, "GBP": 0.79}


@pytest.mark.asyncio
async def test_fetch_rates_returns_empty_on_warn_status(mocker):
    # 429 is in _WARN_STATUSES → logs WARNING, returns {}
    _mock_http(mocker, 429)
    rates = await _fetch_rates()
    assert rates == {}


@pytest.mark.asyncio
async def test_fetch_rates_returns_empty_on_error_status(mocker):
    # 500 is not in _WARN_STATUSES → logs ERROR, returns {}
    _mock_http(mocker, 500)
    rates = await _fetch_rates()
    assert rates == {}


# ── get_rates ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_rates_fetches_on_cache_miss(mocker):
    mock_fetch = mocker.patch("services.currency._fetch_rates", AsyncMock(return_value={"EUR": 0.92}))
    rates = await get_rates()
    mock_fetch.assert_called_once()
    assert rates == {"EUR": 0.92}


@pytest.mark.asyncio
async def test_get_rates_caches_result(mocker):
    mocker.patch("services.currency._fetch_rates", AsyncMock(return_value={"EUR": 0.92}))
    await get_rates()
    assert _mod._RATES_CACHE == {"EUR": 0.92}
    assert _mod._cache_ts > 0


@pytest.mark.asyncio
async def test_get_rates_uses_cache_on_hit(mocker):
    _mod._RATES_CACHE = {"EUR": 0.92}
    _mod._cache_ts = time.monotonic()  # fresh
    mock_fetch = mocker.patch("services.currency._fetch_rates", AsyncMock())

    rates = await get_rates()

    mock_fetch.assert_not_called()
    assert rates == {"EUR": 0.92}


@pytest.mark.asyncio
async def test_get_rates_preserves_old_cache_when_fetch_returns_empty(mocker):
    _mod._RATES_CACHE = {"EUR": 0.92}
    _mod._cache_ts = 0.0  # expired — will trigger a fetch
    mocker.patch("services.currency._fetch_rates", AsyncMock(return_value={}))

    rates = await get_rates()

    assert rates == {"EUR": 0.92}  # old cache not overwritten


# ── to_usd ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_to_usd_converts_via_rates(mocker):
    mocker.patch("services.currency.get_rates", AsyncMock(return_value={"EUR": 0.92}))
    result = await to_usd(9.20, "€")
    assert result == pytest.approx(10.0, rel=1e-2)


@pytest.mark.asyncio
async def test_to_usd_returns_none_for_unknown_currency(mocker):
    mocker.patch("services.currency.get_rates", AsyncMock(return_value={}))
    result = await to_usd(100.0, "XYZ")
    assert result is None
