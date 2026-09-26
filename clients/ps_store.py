import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp

from bot.metrics import ps_api_duration, ps_api_none_results, ps_api_requests
from services.currency import PS_CURRENCY_MAP, PS_ISO_TO_SYMBOL
from services.ps_store import GameInfo, RegionPrice, ps_id_suffix

logger = logging.getLogger(__name__)


class PSStoreAPIError(RuntimeError):
    """Raised when PS Store fails to serve a requested resource."""


# PS Store GQL returns prices in whole major units for these currencies (no /100 needed).
# Add a currency here if displayed price is 100x too small (e.g. Rs 49.99 instead of Rs 4999).
_WHOLE_UNIT_CURRENCIES = {"INR", "JPY", "KRW", "CLP", "COP"}

STORE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

GAME_TYPES = {"FULL_GAME", "PREMIUM_EDITION", "GAME_BUNDLE"}

_GQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
# SHA-256 of GQL persisted queries, embedded in PS Store JS bundles.
# Hardcoded by Sony (Apollo Persisted Queries) — cannot be computed locally.
# If requests start returning 400/errors, extract the new hash from the JS bundle at store.playstation.com.
_GQL_SEARCH_HASH = "6ef5e809c35a056a1150fdcf513d9c505484dd1a946b6208888435c3182f105a"
_GQL_UPSELL_HASH = "a110672db9e20dc4f4d655fffd2f3a09730914ec3458cfb53de70cb2b526af53"
_GQL_CONCEPT_HASH = "cc90404ac049d935afbd9968aef523da2b6723abfb9d586e5f77ebf7c5289006"

_GQL_SEARCH_PAGE_SIZE = 50

_WARN_STATUSES = {403, 404, 410, 429}


_PRICE_RE = re.compile(r'^(?P<prefix>[^\d,.]*)(?P<number>[\d.,]+)(?P<suffix>[^\d,.]*)$')


def _parse_price(price_str: str) -> tuple[float | None, str | None]:
    normalized = price_str.replace(" ", " ").strip()
    normalized = re.sub(r"(?<=\d) (?=\d)", "", normalized)
    m = _PRICE_RE.match(normalized)
    if not m:
        return None, None

    prefix = m.group("prefix").strip()
    number = m.group("number")
    suffix = m.group("suffix").strip()
    currency = prefix or suffix or None

    if "," in number and "." in number:
        if number.rindex(",") > number.rindex("."):
            # "1.899,00" — period=thousands, comma=decimal
            number = number.replace(".", "").replace(",", ".")
        else:
            # "1,899.00" — comma=thousands
            number = number.replace(",", "")
    elif "," in number:
        last_part = number.rsplit(",", 1)[-1]
        if len(last_part) == 2:
            # "466,78" — comma=decimal (exactly 2 digits after comma)
            number = number.replace(",", ".")
        else:
            # "4,999" or "1,234,567" — comma=thousands
            number = number.replace(",", "")

    try:
        return float(number), currency
    except ValueError:
        return None, None


def _canonical_currency(currency: str | None) -> str | None:
    if currency is None:
        return None
    iso = PS_ISO_TO_SYMBOL.get(PS_CURRENCY_MAP.get(currency, currency))
    return iso if iso is not None else currency


_NO_PRICE_STRINGS = {"Free", "Unavailable"}


def _is_free_game(price_data: dict) -> bool:
    """True when the product is truly free with no paid option (should be skipped)."""
    return (
        price_data.get("isFree", False)
        and price_data.get("discountedPrice") == "Free"
        and price_data.get("basePrice", "Free") in (None, "", "Free")
    )


def _parse_str_price_data(price_data: dict) -> tuple[float | None, str | None, float | None]:
    """Parse string-format price data from search results → (price, currency, base_price)."""
    discounted_str = price_data.get("discountedPrice")
    base_str = price_data.get("basePrice")

    price, currency = (
        _parse_price(discounted_str)
        if discounted_str and discounted_str not in _NO_PRICE_STRINGS
        else (None, None)
    )
    base_price, base_currency = (
        _parse_price(base_str)
        if base_str and base_str not in _NO_PRICE_STRINGS
        else (None, None)
    )

    if price is None:
        return base_price, _canonical_currency(base_currency), None

    if base_price == price:
        base_price = None

    return price, _canonical_currency(currency), base_price


def _extract_cover(media: list[dict]) -> str | None:
    for role in ("MASTER", "EDITION_KEY_ART", "FOUR_BY_THREE_BANNER"):
        for item in media:
            if item.get("role") == role and item.get("type") == "IMAGE":
                return item["url"]
    return None


def _parse_end_time(value: int | str | None) -> datetime | None:
    """Parse PS Store endTime (Unix ms as int or numeric string) → datetime (UTC)."""
    if value is None:
        return None
    try:
        ms = int(value) if isinstance(value, str) and value.isdigit() else value
        if isinstance(ms, (int, float)):
            ts = ms / 1000 if ms > 1e10 else ms
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass
    return None


def _make_game_info(product: dict) -> GameInfo:
    return GameInfo(
        title=product.get("name", ""),
        platforms=product.get("platforms") or [],
        type=product.get("storeDisplayClassification"),
        cover_url=_extract_cover(product.get("media") or []),
        ps_id_suffix=ps_id_suffix(product.get("id")),
    )


def _make_region_price(
    price: float | None,
    currency: str | None,
    base_price: float | None,
    discount_text: str | None,
    ps_id: str | None = None,
    discount_end: datetime | None = None,
) -> RegionPrice:
    return RegionPrice(
        price=price,
        currency=currency,
        base_price=base_price,
        discount_text=discount_text,
        ps_id=ps_id,
        discount_end=discount_end,
    )


def _locale_header(region: str) -> str:
    lang, _, country = region.partition("-")
    return f"{lang}-{country.upper()}" if country else region


def _gql_headers(region: str, referer: str) -> dict:
    return {
        **STORE_HEADERS,
        "Origin": "https://store.playstation.com",
        "Referer": referer,
        "apollo-require-preflight": "true",
        "x-psn-store-locale-override": _locale_header(region),
    }


_PURCHASE_CTA_TYPES = frozenset({"ADD_TO_CART", "PREORDER"})

# Returns the price dict for the first outright purchase CTA, or None if the game
# is unavailable in the region (UNAVAILABLE type) or only free/PS Plus options exist.
# PREORDER is treated identically to ADD_TO_CART — pre-order prices are real prices.
def _outright_price(webctas: list[dict]) -> dict | None:
    for cta in webctas:
        if cta.get("type") not in _PURCHASE_CTA_TYPES:
            continue
        if (cta.get("meta") or {}).get("upSellService") not in ("NONE", None):
            continue
        price = cta.get("price")
        if price and not price.get("isFree"):
            return price
    return None


def _make_cta_region_price(price_cta: dict, ps_id: str) -> RegionPrice:
    iso = price_cta.get("currencyCode")
    divisor = 1 if iso in _WHOLE_UNIT_CURRENCIES else 100
    discounted_value = price_cta.get("discountedValue")
    base_value = price_cta.get("basePriceValue")
    price = (discounted_value if discounted_value is not None else base_value or 0) / divisor or None
    base_price = (
        base_value / divisor
        if base_value is not None and base_value != discounted_value
        else None
    )
    return _make_region_price(
        price=price,
        currency=PS_ISO_TO_SYMBOL.get(iso, iso),
        base_price=base_price,
        discount_text=price_cta.get("discountText"),
        ps_id=ps_id,
        discount_end=_parse_end_time(price_cta.get("endTime")),
    )


async def get_concept_default_product_id(
    concept_id: str, region: str = "en-us"
) -> str | None:
    params = urlencode({
        "operationName": "metGetConceptById",
        "variables": json.dumps({"conceptId": concept_id}),
        "extensions": json.dumps({
            "persistedQuery": {"version": 1, "sha256Hash": _GQL_CONCEPT_HASH}
        }),
    })
    referer = f"https://store.playstation.com/{region}/concept/{concept_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_GQL_URL}?{params}",
            headers=_gql_headers(region, referer),
        ) as resp:
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(
                    level,
                    "get_concept_default_product_id: HTTP %d [concept_id=%s region=%s]",
                    resp.status,
                    concept_id,
                    region,
                )
                raise PSStoreAPIError(
                    "PS Store concept request failed "
                    f"(status={resp.status}, concept_id={concept_id}, region={region})"
                )
            data = await resp.json(content_type=None)

    concept = (data.get("data") or {}).get("conceptRetrieve") or {}
    return (concept.get("defaultProduct") or {}).get("id")


async def list_concept_editions(
    concept_id: str, region: str = "en-us"
) -> list[tuple[GameInfo, RegionPrice]]:
    default_id = await get_concept_default_product_id(concept_id, region)
    if default_id is None:
        return []

    params = urlencode({
        "operationName": "productRetrieveForUpsellWithCtas",
        "variables": json.dumps({"productId": default_id}),
        "extensions": json.dumps({
            "persistedQuery": {"version": 1, "sha256Hash": _GQL_UPSELL_HASH}
        }),
    })
    referer = f"https://store.playstation.com/{region}/product/{default_id}/"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_GQL_URL}?{params}",
            headers=_gql_headers(region, referer),
        ) as resp:
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(
                    level,
                    "list_concept_editions: HTTP %d [concept_id=%s region=%s]",
                    resp.status,
                    concept_id,
                    region,
                )
                raise PSStoreAPIError(
                    "PS Store editions request failed "
                    f"(status={resp.status}, concept_id={concept_id}, region={region})"
                )
            data = await resp.json(content_type=None)

    retrieve = (data.get("data") or {}).get("productRetrieve") or {}
    products = (retrieve.get("concept") or {}).get("products") or []
    results: list[tuple[GameInfo, RegionPrice]] = []
    for product in products:
        if product.get("storeDisplayClassification") not in GAME_TYPES:
            continue
        price_cta = _outright_price(product.get("webctas") or [])
        if price_cta is None:
            continue
        ps_id = product.get("id")
        results.append((
            _make_game_info(product),
            _make_cta_region_price(price_cta, ps_id),
        ))
    return results


# Core search implementation — accepts a caller-supplied session so that
# scripts running many concurrent requests can share a single connection pool.
async def _search_games(
    session: aiohttp.ClientSession,
    query: str,
    region: str = "en-us",
    page_size: int = _GQL_SEARCH_PAGE_SIZE,
) -> list[tuple[GameInfo, RegionPrice]]:
    _, _, country = region.partition("-")
    params = urlencode({
        "operationName": "getSearchResults",
        "variables": json.dumps({
            "countryCode": country.upper() if country else region.upper(),
            "languageCode": "en",
            "pageSize": page_size,
            "searchTerm": query,
            "nextCursor": "",
            "pageOffset": 0,
        }),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_SEARCH_HASH}}),
    })
    headers = _gql_headers(region, "https://store.playstation.com/")
    words = [w.lower() for w in query.split() if w]

    # Whole-word patterns — avoids substring false positives:
    # e.g. "1" matching "11", "24" matching "2024", "v" matching "vr".
    word_patterns = [re.compile(r"\b" + re.escape(w) + r"\b") for w in words]
    # Whole-word "demo" check — skips demo listings that the PS Store sometimes
    # classifies as FULL_GAME/GAME_BUNDLE (common in de-de region).
    # \bdemo\b avoids false positives like "Demolition" or "Democracy".
    _demo_re = re.compile(r"\bdemo\b")

    _t0 = time.monotonic()
    async with session.get(f"{_GQL_URL}?{params}", headers=headers) as resp:
        _status = resp.status
        if resp.status != 200:
            level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
            logger.log(level, "search_games: HTTP %d [query=%r region=%s]", resp.status, query, region)
            ps_api_requests.labels(operation="search", status=str(_status)).inc()
            ps_api_duration.labels(operation="search").observe(time.monotonic() - _t0)
            ps_api_none_results.labels(operation="search").inc()
            return []
        data = await resp.json(content_type=None)
    ps_api_requests.labels(operation="search", status="200").inc()
    ps_api_duration.labels(operation="search").observe(time.monotonic() - _t0)

    page = (data.get("data") or {}).get("universalSearch")
    if not page:
        logger.warning("search_games: no universalSearch data [query=%r region=%s]", query, region)
        ps_api_none_results.labels(operation="search").inc()
        return []

    results: list[tuple[GameInfo, RegionPrice]] = []
    for product in page.get("results", []):
        if product.get("storeDisplayClassification") not in GAME_TYPES:
            continue
        name_lower = product.get("name", "").lower()
        if not all(p.search(name_lower) for p in word_patterns):
            continue
        if _demo_re.search(name_lower):
            logger.debug(
                "search_games: skipping demo listing [ps_id=%s name=%r region=%s]",
                product["id"], product.get("name"), region,
            )
            continue
        price_data = product.get("price") or {}
        if _is_free_game(price_data):
            continue
        price, currency, base_price = _parse_str_price_data(price_data)
        if price is None:
            # Empty price object (delisted) or explicit "not available" string in any
            # locale — both are expected, not actionable. Log at DEBUG only.
            logger.debug(
                "search_games: no price — unavailable or delisted [ps_id=%s name=%r region=%s]",
                product["id"], product.get("name"), region,
            )
            continue

        discount_text = price_data.get("discountText")
        discount_end = _parse_end_time(price_data.get("endTime"))
        results.append((
            _make_game_info(product),
            _make_region_price(price, currency, base_price, discount_text, product["id"], discount_end),
        ))

    logger.info("search_games: %d results [query=%r region=%s]", len(results), query, region)
    return results


# Public wrapper — creates its own session so callers don't need to manage one.
async def search_games(
    query: str, region: str = "en-us", page_size: int = _GQL_SEARCH_PAGE_SIZE
) -> list[tuple[GameInfo, RegionPrice]]:
    async with aiohttp.ClientSession() as session:
        return await _search_games(session, query, region, page_size)


# Fetches full product data for a known ps_id in a specific region.
# Returns (GameInfo, RegionPrice) if the game exists and has a purchasable price.
# Returns None if the product is not found, the region doesn't carry it (UNAVAILABLE),
# or the game has no paid CTA (free or PS Plus only).
async def get_game_info(ps_id: str, region: str = "en-us") -> tuple[GameInfo, RegionPrice] | None:
    params = urlencode({
        "operationName": "productRetrieveForUpsellWithCtas",
        "variables": json.dumps({"productId": ps_id}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_UPSELL_HASH}}),
    })

    _t0 = time.monotonic()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_GQL_URL}?{params}",
            headers=_gql_headers(region, f"https://store.playstation.com/{region}/product/{ps_id}/"),
        ) as resp:
            _status = resp.status
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(level, "get_game_info: HTTP %d [ps_id=%s region=%s]", resp.status, ps_id, region)
                ps_api_requests.labels(operation="get_game_info", status=str(_status)).inc()
                ps_api_duration.labels(operation="get_game_info").observe(time.monotonic() - _t0)
                ps_api_none_results.labels(operation="get_game_info").inc()
                return None
            data = await resp.json(content_type=None)
    ps_api_requests.labels(operation="get_game_info", status="200").inc()
    ps_api_duration.labels(operation="get_game_info").observe(time.monotonic() - _t0)

    retrieve = (data.get("data") or {}).get("productRetrieve")
    if not retrieve:
        logger.warning("get_game_info: product not found [ps_id=%s region=%s]", ps_id, region)
        ps_api_none_results.labels(operation="get_game_info").inc()
        return None

    products = (retrieve.get("concept") or {}).get("products") or []
    product = next((p for p in products if p.get("id") == ps_id), None)
    if not product:
        logger.warning(
            "get_game_info: product not in concept.products [ps_id=%s region=%s]",
            ps_id, region,
        )
        ps_api_none_results.labels(operation="get_game_info").inc()
        return None

    webctas = product.get("webctas") or []
    price_cta = _outright_price(webctas)
    if price_cta is None:
        return None

    region_price = _make_cta_region_price(price_cta, ps_id)

    logger.info("get_game_info: found %r [ps_id=%s region=%s]", product.get("name"), ps_id, region)
    return _make_game_info(product), region_price
