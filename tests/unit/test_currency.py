import time
from unittest.mock import AsyncMock

import pytest

import services.currency as _mod
from services.currency import _fetch_rates, find_currency_suggestions, get_rates


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


# ── find_currency_suggestions ─────────────────────────────────────────────────

_RATES = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "RUB": 73.3, "BYN": 2.77, "AUD": 1.43, "CAD": 1.41}


def test_find_by_code_prefix():
    results = find_currency_suggestions("RU", _RATES)
    codes = [r[0] for r in results]
    assert "RUB" in codes


def test_find_by_name_substring():
    results = find_currency_suggestions("ruble", _RATES)
    codes = [r[0] for r in results]
    assert "RUB" in codes
    assert "BYN" in codes


def test_code_prefix_comes_before_name_match():
    # "AU" matches AUD by prefix and "Australian Dollar" by name — prefix wins position
    rates = {"AUD": 1.43, "UAH": 44.9}  # UAH name contains no "au", AUD code starts with AU
    results = find_currency_suggestions("AU", rates)
    codes = [r[0] for r in results]
    assert codes[0] == "AUD"


def test_returns_name_from_pycountry():
    results = find_currency_suggestions("EUR", _RATES)
    assert results == [("EUR", "Euro")]


def test_unknown_iso_falls_back_to_code_as_name(mocker):
    mocker.patch("services.currency.pycountry.currencies.get", return_value=None)
    results = find_currency_suggestions("CN", {"CNH": 6.77})
    assert results == [("CNH", "CNH")]


def test_short_query_does_not_search_by_name():
    # "ru" is 2 chars — should not match BYN via "Belarusian Ruble"
    results = find_currency_suggestions("ru", _RATES)
    codes = [r[0] for r in results]
    assert "BYN" not in codes
    assert "RUB" in codes  # still matches by code prefix


def test_no_match_returns_empty():
    results = find_currency_suggestions("ZZZ", _RATES)
    assert results == []


def test_excludes_codes_not_in_rates():
    results = find_currency_suggestions("EU", {"USD": 1.0})  # EUR not in rates
    codes = [r[0] for r in results]
    assert "EUR" not in codes


def test_respects_max_suggestions(mocker):
    # 15 codes all starting with "A"
    rates = {f"A{chr(65+i)}{chr(65+i)}": 1.0 for i in range(15)}
    results = find_currency_suggestions("A", rates)
    assert len(results) <= _mod._MAX_SUGGESTIONS
