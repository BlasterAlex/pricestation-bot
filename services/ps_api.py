import time

import aiohttp

_REGIONS_URL = (
    "https://www.playstation.com/content.country-selector.json/?locale=en-us"
)
_CACHE_TTL = 6 * 3600  # 6 hours

_cache: list[dict] | None = None
_cache_at: float = 0.0


async def get_ps_regions() -> list[dict]:
    """Return a flat list of {"name": ..., "locale": ...} dicts from the PS API.

    Result is cached in memory for _CACHE_TTL seconds.
    """
    global _cache, _cache_at

    if _cache is not None and time.monotonic() - _cache_at < _CACHE_TTL:
        return _cache

    async with aiohttp.ClientSession() as http:
        async with http.get(_REGIONS_URL) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

    countries: list[dict] = []
    for group in data.get("regions", []):
        for country in group.get("countries", []):
            countries.append(
                {
                    "name": country["countryName"],
                    "locale": country["localeCode"],
                }
            )

    _cache = countries
    _cache_at = time.monotonic()
    return _cache
