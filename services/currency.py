import time

import aiohttp

# PS Store currency string → ISO 4217 code
PS_CURRENCY_MAP: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₩": "KRW",
    "₺": "TRY",
    "TL": "TRY",
    "Rs": "INR",
    "R$": "BRL",
    "A$": "AUD",
    "C$": "CAD",
    "zł": "PLN",
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
}

_RATES_CACHE: dict[str, float] = {}
_CACHE_TTL = 3600  # 1 hour
_cache_ts: float = 0.0


async def _fetch_rates() -> dict[str, float]:
    url = "https://api.frankfurter.dev/v1/latest?from=USD"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
    rates = data["rates"]
    rates["USD"] = 1.0
    return rates


async def get_rates() -> dict[str, float]:
    global _RATES_CACHE, _cache_ts
    if not _RATES_CACHE or time.monotonic() - _cache_ts > _CACHE_TTL:
        _RATES_CACHE = await _fetch_rates()
        _cache_ts = time.monotonic()
    return _RATES_CACHE


def convert_to_usd(amount: float, ps_currency: str, rates: dict[str, float]) -> float | None:
    iso = PS_CURRENCY_MAP.get(ps_currency)
    if not iso:
        return None
    if iso == "USD":
        return round(amount, 2)
    rate = rates.get(iso)
    if not rate:
        return None
    return round(amount / rate, 2)


async def to_usd(amount: float, ps_currency: str) -> float | None:
    rates = await get_rates()
    return convert_to_usd(amount, ps_currency, rates)
