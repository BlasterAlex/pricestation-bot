import logging
import time

import aiohttp

_WARN_STATUSES = {403, 404, 410, 429}

logger = logging.getLogger(__name__)

# PS Store currency string → ISO 4217 code
PS_CURRENCY_MAP: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₩": "KRW",
    "원": "KRW",
    "₺": "TRY",
    "TL": "TRY",
    "Rs": "INR",
    "R$": "BRL",
    "A$": "AUD",
    "C$": "CAD",
    "zł": "PLN",
    "zl": "PLN",
    "kr": "SEK",
    "CHF": "CHF",
    "CZK": "CZK",
    "HUF": "HUF",
    "NOK": "NOK",
    "DKK": "DKK",
    "MXN": "MXN",
    "ARS": "ARS",
    "CLP": "CLP",
    "COP": "COP",
    "UAH": "UAH",
}

# ISO 4217 code → PS Store display symbol
PS_ISO_TO_SYMBOL: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "KRW": "₩",
    "TRY": "TL",
    "INR": "Rs",
    "BRL": "R$",
    "AUD": "A$",
    "CAD": "C$",
    "PLN": "zł",
    "SEK": "kr",
    "CHF": "CHF",
    "CZK": "CZK",
    "HUF": "HUF",
    "NOK": "NOK",
    "DKK": "DKK",
    "MXN": "MXN",
    "ARS": "ARS",
    "CLP": "CLP",
    "COP": "COP",
    "UAH": "UAH",
}

_RATES_CACHE: dict[str, float] = {}
_CACHE_TTL = 3600  # 1 hour
_cache_ts: float = 0.0


async def _fetch_rates() -> dict[str, float]:
    url = "https://open.er-api.com/v6/latest/USD"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(level, "get_rates: HTTP %d", resp.status)
                return {}
            data = await resp.json()
    rates = data["rates"]
    logger.info("Exchange rates updated (%d currencies)", len(rates))
    return rates


async def get_rates() -> dict[str, float]:
    global _RATES_CACHE, _cache_ts
    if not _RATES_CACHE or time.monotonic() - _cache_ts > _CACHE_TTL:
        rates = await _fetch_rates()
        if rates:
            _RATES_CACHE = rates
            _cache_ts = time.monotonic()
    return _RATES_CACHE


def convert_to_usd(amount: float, ps_currency: str, rates: dict[str, float]) -> float | None:
    iso = PS_CURRENCY_MAP.get(ps_currency, ps_currency)
    if iso == "USD":
        return round(amount, 2)
    rate = rates.get(iso)
    if not rate:
        return None
    return round(amount / rate, 2)


async def to_usd(amount: float, ps_currency: str) -> float | None:
    rates = await get_rates()
    return convert_to_usd(amount, ps_currency, rates)
