import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp

from services.currency import PS_CURRENCY_MAP, PS_ISO_TO_SYMBOL

logger = logging.getLogger(__name__)

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

_GQL_SEARCH_PAGE_SIZE = 50

_WARN_STATUSES = {403, 404, 410, 429}


# Removes punctuation, trademark symbols, non-ASCII characters (Cyrillic, CJK,
# locale prefixes like "Набір", etc.), and whitespace so that titles collapse
# to the same key regardless of regional language prefix.
def normalize_title(title: str) -> str:
    t = re.sub(r"[™®©:().,'\"!?\-/]", "", title.lower())
    t = re.sub(r"[^\x00-\x7f]", "", t)
    return re.sub(r"\s+", "", t)


@dataclass
class RegionPrice:
    price: float | None
    currency: str | None
    base_price: float | None
    discount_text: str | None
    ps_id: str | None = None
    discount_end: str | None = None

    def to_dict(self) -> dict:
        return {
            "price": self.price,
            "currency": self.currency,
            "base_price": self.base_price,
            "discount_text": self.discount_text,
            "ps_id": self.ps_id,
            "discount_end": self.discount_end,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegionPrice":
        return cls(**d)


@dataclass
class GameInfo:
    title: str
    platforms: list[str]
    type: str
    cover_url: str | None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "platforms": self.platforms,
            "type": self.type,
            "cover_url": self.cover_url,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameInfo":
        return cls(**d)


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


def _parse_str_price_data(price_data: dict) -> tuple[float | None, str | None, float | None, str | None]:
    """Parse string-format price data from search results → (price, currency, base_price, discount_text)."""
    discounted_str = price_data.get("discountedPrice")
    base_str = price_data.get("basePrice")
    is_free = price_data.get("isFree", False)

    # "Free" in discountedPrice with isFree=False means free trial — use basePrice as the real price.
    if is_free and discounted_str == "Free" and (not base_str or base_str == "Free"):
        return None, None, None, None

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
        return base_price, _canonical_currency(base_currency), None, price_data.get("discountText")

    if base_price == price:
        base_price = None

    return price, _canonical_currency(currency), base_price, price_data.get("discountText")


def _extract_cover(media: list[dict]) -> str | None:
    for role in ("MASTER", "EDITION_KEY_ART", "FOUR_BY_THREE_BANNER"):
        for item in media:
            if item.get("role") == role and item.get("type") == "IMAGE":
                return item["url"]
    return None


def _parse_end_time(value: int | str | None) -> str | None:
    """Parse PS Store endTime (Unix ms as int or numeric string) → 'YYYY-MM-DD HH:MM' (UTC)."""
    if value is None:
        return None
    try:
        from datetime import datetime, timezone
        ms = int(value) if isinstance(value, str) and value.isdigit() else value
        if isinstance(ms, (int, float)):
            ts = ms / 1000 if ms > 1e10 else ms
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        if isinstance(value, str) and len(value) >= 10:
            return value[:16]
    except Exception:
        pass
    return None


def _make_game_info(product: dict) -> GameInfo:
    return GameInfo(
        title=product.get("name", ""),
        platforms=product.get("platforms") or [],
        type=product.get("storeDisplayClassification"),
        cover_url=_extract_cover(product.get("media") or []),
    )


def _make_region_price(
    price: float | None,
    currency: str | None,
    base_price: float | None,
    discount_text: str | None,
    ps_id: str | None = None,
    discount_end: str | None = None,
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


def _outright_price(webctas: list[dict]) -> dict | None:
    for cta in webctas:
        if cta.get("type") == "ADD_TO_CART":
            if (cta.get("meta") or {}).get("upSellService") == "NONE":
                price = cta.get("price")
                if not (price or {}).get("isFree"):
                    return price
    return None


async def search_games(query: str, region: str = "en-us") -> list[tuple[GameInfo, RegionPrice]]:
    _, _, country = region.partition("-")
    params = urlencode({
        "operationName": "getSearchResults",
        "variables": json.dumps({
            "countryCode": country.upper() if country else region.upper(),
            "languageCode": "en",
            "pageSize": _GQL_SEARCH_PAGE_SIZE,
            "searchTerm": query,
            "nextCursor": "",
            "pageOffset": 0,
        }),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_SEARCH_HASH}}),
    })
    headers = _gql_headers(region, "https://store.playstation.com/")
    words = [w.lower() for w in query.split() if w]

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{_GQL_URL}?{params}", headers=headers) as resp:
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(level, "search_games: HTTP %d [query=%r region=%s]", resp.status, query, region)
                return []
            data = await resp.json(content_type=None)

    page = (data.get("data") or {}).get("universalSearch")
    if not page:
        logger.warning("search_games: no universalSearch data [query=%r region=%s]", query, region)
        return []

    results: list[tuple[GameInfo, RegionPrice]] = []
    for product in page.get("results", []):
        if product.get("storeDisplayClassification") not in GAME_TYPES:
            continue
        if not all(w in product.get("name", "").lower() for w in words):
            continue
        price_data = product.get("price") or {}
        price, currency, base_price, discount_text = _parse_str_price_data(price_data)
        discounted = price_data.get("discountedPrice")
        if price is None and not price_data.get("isFree") and discounted not in _NO_PRICE_STRINGS:
            logger.warning(
                "search_games: no price parsed [ps_id=%s region=%s raw=%r]",
                product["id"], region, price_data,
            )
        discount_end = _parse_end_time(price_data.get("endTime"))
        results.append((
            _make_game_info(product),
            _make_region_price(price, currency, base_price, discount_text, product["id"], discount_end),
        ))

    logger.info("search_games: %d results [query=%r region=%s]", len(results), query, region)
    return results


async def get_game_info(ps_id: str, region: str = "en-us") -> tuple[GameInfo, RegionPrice | None] | None:
    params = urlencode({
        "operationName": "productRetrieveForUpsellWithCtas",
        "variables": json.dumps({"productId": ps_id}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_UPSELL_HASH}}),
    })

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_GQL_URL}?{params}",
            headers=_gql_headers(region, f"https://store.playstation.com/{region}/product/{ps_id}/"),
        ) as resp:
            if resp.status != 200:
                level = logging.WARNING if resp.status in _WARN_STATUSES else logging.ERROR
                logger.log(level, "get_game_info: HTTP %d [ps_id=%s region=%s]", resp.status, ps_id, region)
                return None
            data = await resp.json(content_type=None)

    retrieve = (data.get("data") or {}).get("productRetrieve")
    if not retrieve:
        logger.warning("get_game_info: product not found [ps_id=%s region=%s]", ps_id, region)
        return None

    products = (retrieve.get("concept") or {}).get("products") or []
    product = next((p for p in products if p.get("id") == ps_id), None)
    if not product:
        logger.warning("get_game_info: product not in concept.products [ps_id=%s region=%s]", ps_id, region)
        return None

    region_price: RegionPrice | None = None
    webctas = product.get("webctas") or []
    price_cta = _outright_price(webctas)
    if price_cta is None:
        logger.warning(
            "get_game_info: no purchasable CTA [ps_id=%s region=%s webctas=%r]",
            ps_id, region, webctas,
        )
    if price_cta and not price_cta.get("isFree"):
        iso = price_cta.get("currencyCode")
        divisor = 1 if iso in _WHOLE_UNIT_CURRENCIES else 100
        dv = price_cta.get("discountedValue")
        bv = price_cta.get("basePriceValue")
        price = (dv if dv is not None else bv or 0) / divisor or None
        base_price = bv / divisor if bv is not None and bv != dv else None
        region_price = _make_region_price(
            price=price,
            currency=PS_ISO_TO_SYMBOL.get(iso, iso),
            base_price=base_price,
            discount_text=price_cta.get("discountText"),
            ps_id=ps_id,
            discount_end=_parse_end_time(price_cta.get("endTime")),
        )

    logger.info("get_game_info: found %r [ps_id=%s region=%s]", product.get("name"), ps_id, region)
    return _make_game_info(product), region_price


async def get_game_price(ps_id: str, region: str = "en-us") -> float | None:
    result = await get_game_info(ps_id, region)
    if result is None:
        return None
    _, region_price = result
    return region_price.price if region_price else None
