import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp

from services.currency import PS_ISO_TO_SYMBOL

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

GAME_TYPES = {"FULL_GAME", "PREMIUM_EDITION", "GAME_BUNDLE"}

_GQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
# SHA-256 of the `productRetrieveForUpsellWithCtas` GQL query, embedded in PS Store JS bundles.
# Hardcoded by Sony (Apollo Persisted Queries) — cannot be computed locally.
# If requests start returning 400/errors, extract the new hash from the JS bundle at store.playstation.com.
_GQL_UPSELL_HASH = "a110672db9e20dc4f4d655fffd2f3a09730914ec3458cfb53de70cb2b526af53"


@dataclass
class GameResult:
    ps_id: str
    title: str
    platforms: list[str]
    type: str
    price: float | None
    currency: str | None
    base_price: float | None
    discount_text: str | None
    cover_url: str | None

    def to_dict(self) -> dict:
        return {
            "ps_id": self.ps_id,
            "title": self.title,
            "platforms": self.platforms,
            "type": self.type,
            "price": self.price,
            "currency": self.currency,
            "base_price": self.base_price,
            "discount_text": self.discount_text,
            "cover_url": self.cover_url,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameResult":
        return cls(**d)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


_PRICE_RE = re.compile(r'^(?P<prefix>[^\d,.]*)(?P<number>[\d.,]+)(?P<suffix>[^\d,.]*)$')


def _parse_price(price_str: str) -> tuple[float | None, str | None]:
    normalized = price_str.replace(" ", " ").strip()
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


def _extract_cover(media: list[dict]) -> str | None:
    for role in ("MASTER", "EDITION_KEY_ART", "FOUR_BY_THREE_BANNER"):
        for item in media:
            if item.get("role") == role and item.get("type") == "IMAGE":
                return item["url"]
    return None


def _locale_header(region: str) -> str:
    lang, _, country = region.partition("-")
    return f"{lang}-{country.upper()}" if country else region


def _outright_price(webctas: list[dict]) -> dict | None:
    for cta in webctas:
        if cta.get("type") == "ADD_TO_CART":
            if (cta.get("meta") or {}).get("upSellService") == "NONE":
                return cta.get("price")
    return None


def _resolve_product(apollo: dict, ref: str) -> GameResult | None:
    raw = apollo.get(ref)
    if not raw or raw.get("__typename") != "Product":
        return None

    media = raw.get("media") or []
    price_data = raw.get("price") or {}

    discounted_str = price_data.get("discountedPrice")
    base_str = price_data.get("basePrice")

    price, currency = _parse_price(discounted_str) if discounted_str and discounted_str != "Free" else (None, None)
    base_price, _ = _parse_price(base_str) if base_str and base_str != "Free" else (None, None)

    if base_price == price:
        base_price = None

    return GameResult(
        ps_id=raw["id"],
        title=raw["name"],
        platforms=raw.get("platforms", []),
        type=raw.get("storeDisplayClassification"),
        price=price,
        currency=currency,
        base_price=base_price,
        discount_text=price_data.get("discountText"),
        cover_url=_extract_cover(media),
    )


async def search_games(query: str, region: str = "en-us") -> list[GameResult]:
    url = f"https://store.playstation.com/{region}/search/{query}"

    async with aiohttp.ClientSession(headers=STORE_HEADERS) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            html = await resp.text()

    match = NEXT_DATA_RE.search(html)
    if not match:
        return []

    data = json.loads(match.group(1))
    apollo: dict = data.get("props", {}).get("apolloState", {})
    root: dict = apollo.get("ROOT_QUERY", {})

    search_data: dict | None = None
    for key, val in root.items():
        if "universalSearch" in key and isinstance(val, dict):
            search_data = val
            break

    if not search_data:
        logger.warning("search_games: no universalSearch data [query=%r region=%s]", query, region)
        return []

    words = [w.lower() for w in query.split() if w]

    results = []
    for ref_obj in search_data.get("results", []):
        ref = ref_obj.get("__ref", "")
        product = _resolve_product(apollo, ref)
        if not product or product.type not in GAME_TYPES:
            continue
        title_lower = product.title.lower()
        if all(w in title_lower for w in words):
            results.append(product)

    logger.info("search_games: %d results [query=%r region=%s]", len(results), query, region)
    return results


async def get_game_info(ps_id: str, region: str = "en-us") -> GameResult | None:
    params = urlencode({
        "operationName": "productRetrieveForUpsellWithCtas",
        "variables": json.dumps({"productId": ps_id}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_UPSELL_HASH}}),
    })
    headers = {
        **STORE_HEADERS,
        "Origin": "https://store.playstation.com",
        "Referer": f"https://store.playstation.com/{region}/product/{ps_id}/",
        "apollo-require-preflight": "true",
        "x-psn-store-locale-override": _locale_header(region),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{_GQL_URL}?{params}", headers=headers) as resp:
            if resp.status != 200:
                logger.warning("get_game_info: HTTP %d [ps_id=%s region=%s]", resp.status, ps_id, region)
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

    price, currency, base_price, discount_text = None, None, None, None
    price_cta = _outright_price(product.get("webctas") or [])
    if price_cta and not price_cta.get("isFree"):
        iso = price_cta.get("currencyCode")
        divisor = 1 if iso in _WHOLE_UNIT_CURRENCIES else 100
        dv = price_cta.get("discountedValue") or 0
        bv = price_cta.get("basePriceValue") or 0
        price = dv / divisor if dv else None
        base_price = bv / divisor if bv and bv != dv else None
        currency = PS_ISO_TO_SYMBOL.get(iso, iso)
        discount_text = price_cta.get("discountText")

    logger.info("get_game_info: found %r [ps_id=%s region=%s]", product.get("name"), ps_id, region)
    return GameResult(
        ps_id=ps_id,
        title=product.get("name"),
        platforms=product.get("platforms") or [],
        type=product.get("storeDisplayClassification"),
        price=price,
        currency=currency,
        base_price=base_price,
        discount_text=discount_text,
        cover_url=_extract_cover(product.get("media") or []),
    )


async def get_game_price(ps_id: str, region: str = "en-us") -> float | None:
    result = await get_game_info(ps_id, region)
    return result.price if result else None
