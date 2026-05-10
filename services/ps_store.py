import json
import re

import aiohttp

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
    for item in media:
        if item.get("role") == "MASTER" and item.get("type") == "IMAGE":
            return item["url"]
    return None


def _resolve_product(apollo: dict, ref: str) -> dict | None:
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

    return {
        "ps_id": raw["id"],
        "title": raw["name"],
        "platforms": raw.get("platforms", []),
        "type": raw.get("storeDisplayClassification"),
        "price": price,
        "currency": currency,
        "base_price": base_price,
        "discount_text": price_data.get("discountText"),
        "cover_url": _extract_cover(media),
    }


async def search_games(query: str, region: str = "en-us") -> list[dict]:
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
        return []

    words = [w.lower() for w in query.split() if w]

    results = []
    for ref_obj in search_data.get("results", []):
        ref = ref_obj.get("__ref", "")
        product = _resolve_product(apollo, ref)
        if not product or product["type"] not in GAME_TYPES:
            continue
        title_lower = product["title"].lower()
        if all(w in title_lower for w in words):
            results.append(product)

    return results


async def get_game_price(ps_id: str, region: str = "en-us") -> float | None:
    raise NotImplementedError
