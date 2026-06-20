import logging
import time

import aiohttp
import pycountry

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

DEFAULT_BASE_CURRENCY = "USD"

_MAX_SUGGESTIONS = 10


def find_currency_suggestions(query: str, rates: dict[str, float]) -> list[tuple[str, str]]:
    """Return (alpha_3, name) pairs matching *query* by code prefix or name substring.

    Only codes present in *rates* are returned. Results are sorted: code
    prefix matches first, then name-only matches.
    """
    q = query.upper()
    q_lower = query.lower()

    code_matches: list[tuple[str, str]] = []
    name_matches: list[tuple[str, str]] = []

    search_by_name = len(query) >= 3

    for iso in rates:
        c = pycountry.currencies.get(alpha_3=iso)
        name = c.name if c else iso
        if iso.startswith(q):
            code_matches.append((iso, name))
        elif search_by_name and q_lower in name.lower():
            name_matches.append((iso, name))

    combined = code_matches + name_matches
    return combined[:_MAX_SUGGESTIONS]

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


def convert(
    amount: float,
    from_ps_currency: str,
    to_iso: str,
    rates: dict[str, float],
) -> float | None:
    """Convert *amount* from a PS Store currency symbol to *to_iso* (ISO 4217).

    Rates are relative to USD (open.er-api.com /v6/latest/USD), so USD itself
    is always 1.0 even when absent from the dict.
    """
    from_iso = PS_CURRENCY_MAP.get(from_ps_currency, from_ps_currency)
    if from_iso == to_iso:
        return round(amount, 2)
    from_rate = rates.get(from_iso)
    to_rate = rates.get(to_iso, 1.0 if to_iso == "USD" else None)
    if not from_rate or to_rate is None:
        return None
    return round(amount / from_rate * to_rate, 2)


