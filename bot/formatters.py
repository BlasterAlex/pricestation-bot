from datetime import datetime, timezone

from services.currency import DEFAULT_BASE_CURRENCY, PS_CURRENCY_MAP, PS_ISO_TO_SYMBOL, convert
from services.price_history import UserGameSaleHistory, format_sale_when
from services.ps_store import GameInfo, RegionPrice

TYPE_EMOJI = {
    "FULL_GAME": "🎮",
    "PREMIUM_EDITION": "💎",
    "GAME_BUNDLE": "📦",
}

TYPE_LABEL = {
    "FULL_GAME": "Full Game",
    "PREMIUM_EDITION": "Premium Edition",
    "GAME_BUNDLE": "Game Bundle",
}


def locale_flag(locale: str) -> str:
    country = locale.split("-")[-1].upper()
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country)


def _format_price(amount: float, currency: str) -> str:
    sep = " " if currency.isalpha() else ""
    if amount == int(amount):
        return f"{currency}{sep}{int(amount)}"
    return f"{currency}{sep}{amount:.2f}"


def _base_by_locale(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
    base_currency: str,
) -> dict[str, float | None]:
    result = {}
    for locale, rp in prices.items():
        if rp.price is not None and rp.currency is not None and rates is not None:
            result[locale] = convert(rp.price, rp.currency, base_currency, rates)
        else:
            result[locale] = None
    return result


def _base_str(base_value: float | None, base_currency: str, region_iso: str) -> str:
    if base_value is None or region_iso == base_currency:
        return ""
    symbol = PS_ISO_TO_SYMBOL.get(base_currency, base_currency)
    sep = " " if symbol.isalpha() else ""
    if base_value == int(base_value):
        return f" ({symbol}{sep}{int(base_value)})"
    return f" ({symbol}{sep}{base_value:.2f})"


def _price_line(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> str:
    base_map = _base_by_locale(prices, rates, base_currency)
    cheapest = min(
        (loc for loc, val in base_map.items() if val is not None),
        key=lambda loc: base_map[loc],
        default=None,
    )

    parts = []
    for locale, rp in prices.items():
        flag = locale_flag(locale)
        if rp.price is None or rp.currency is None:
            parts.append(f"{flag} N/A")
            continue

        base_val = base_map.get(locale)
        iso = PS_CURRENCY_MAP.get(rp.currency, rp.currency)
        base_suffix = _base_str(base_val, base_currency, iso)
        strike = f"<s>{_format_price(rp.base_price, rp.currency)}</s> " if rp.base_price is not None else ""
        discount_str = f" {rp.discount_text}" if rp.discount_text else ""
        price_label = f"{strike}{_format_price(rp.price, rp.currency)}{discount_str}{base_suffix}"
        text = f"{flag} {price_label}"

        if locale == cheapest and cheapest is not None and len(prices) > 1:
            text = f"<b>{text}</b>"
        parts.append(text)

    return " · ".join(parts)


def _game_header(game: GameInfo) -> list[str]:
    emoji = TYPE_EMOJI.get(game.type, "🎮")
    type_label = TYPE_LABEL.get(game.type, game.type) or "—"
    platforms = " · ".join(game.platforms) if game.platforms else "—"
    return [f"{emoji} {game.title}", f"{platforms} · {type_label}"]


def _card_price_lines(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
    old_prices: dict[str, float] | None = None,
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> list[str]:
    base_map = _base_by_locale(prices, rates, base_currency)
    cheapest = min(
        (loc for loc, val in base_map.items() if val is not None),
        key=lambda loc: base_map[loc],
        default=None,
    )

    lines = []
    for locale, rp in prices.items():
        flag = locale_flag(locale)
        if rp.price is None or rp.currency is None:
            lines.append(f"{flag} N/A")
            continue

        base_val = base_map.get(locale)
        iso = PS_CURRENCY_MAP.get(rp.currency, rp.currency)
        base_suffix = _base_str(base_val, base_currency, iso)
        strike = f"<s>{_format_price(rp.base_price, rp.currency)}</s> " if rp.base_price is not None else ""
        discount_str = f" {rp.discount_text}" if rp.discount_text else ""
        price_label = f"{strike}{_format_price(rp.price, rp.currency)}{discount_str}{base_suffix}"

        url = f"https://store.playstation.com/{locale}/product/{rp.ps_id}"
        is_cheapest = locale == cheapest and cheapest is not None and len(prices) > 1
        current = f'<a href="{url}">{price_label}</a>'
        if is_cheapest:
            current = f"<b>{current}</b>"
        text = f"{flag} {current}"

        old_price = (old_prices or {}).get(locale)
        if old_price is not None and old_price != rp.price:
            if rp.base_price is None or abs(rp.base_price - old_price) > 0.001:
                old_base = convert(old_price, rp.currency, base_currency, rates) if rates else None
                old_iso = PS_CURRENCY_MAP.get(rp.currency, rp.currency)
                old_base_suffix = _base_str(old_base, base_currency, old_iso)
                arrow = "↓" if rp.price < old_price else "↑"
                text += f"  {arrow} <s>{_format_price(old_price, rp.currency)}{old_base_suffix}</s>"

        lines.append(text)

    return lines


def format_game_list(
    title: str,
    footer: str,
    games: list[GameInfo],
    prices: list[dict[str, RegionPrice]],
    rates: dict[str, float] | None = None,
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> str:
    if not games:
        return "Nothing found. Try a different query."

    cards = []
    for game, game_prices in zip(games, prices):
        lines = _game_header(game)
        if game_prices:
            lines.append(_price_line(game_prices, rates, base_currency))
        cards.append("\n".join(lines))

    return f"{title}\n\n" + "\n\n".join(cards) + f"\n\n{footer}"


def _offer_end_line(prices: dict[str, RegionPrice]) -> str | None:
    for rp in prices.values():
        if rp.discount_end and rp.base_price is not None:
            return _format_offer_end(rp.discount_end)
    return None


def _format_tracking_since(dt) -> str:
    return dt.strftime("%d %b %Y")


def _format_offer_end(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if dt.hour or dt.minute:
        return f"{dt.strftime('%d %b %Y %H:%M')} UTC"
    return dt.strftime("%d %b %Y")


def _format_sale_price(
    price: float,
    region_currency: str,
    rates: dict[str, float] | None,
    base_currency: str,
) -> str:
    native = _format_price(price, region_currency)
    iso = PS_CURRENCY_MAP.get(region_currency, region_currency)
    converted = convert(price, region_currency, base_currency, rates) if rates else None
    return f"{native}{_base_str(converted, base_currency, iso)}"


def format_past_sales_lines(
    sale_history: UserGameSaleHistory | None,
    history_format: str,
    *,
    limit_per_region: int,
    rates: dict[str, float] | None = None,
    base_currency: str = DEFAULT_BASE_CURRENCY,
    show_tracking_footer: bool = True,
) -> list[str]:
    if sale_history is None:
        return []

    lines: list[str] = []
    if sale_history.total_sales > 0:
        lines.append("\n📉 Past sales:")
        for region_hist in sale_history.regions:
            if not region_hist.sales:
                continue
            flag = locale_flag(region_hist.region_code)
            lines.append(f"{flag}")
            for price, recorded_at in region_hist.sales[:limit_per_region]:
                when = format_sale_when(recorded_at, history_format)
                price_label = _format_sale_price(price, region_hist.currency, rates, base_currency)
                lines.append(f"• {price_label} — {when}")

    if show_tracking_footer:
        since = _format_tracking_since(sale_history.tracking_since)
        lines.append(f"\n<i>Tracking since {since}</i>")

    return lines


def format_game_card(
    game: GameInfo,
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None = None,
    old_prices: dict[str, float] | None = None,
    title: str = "",
    footer: str = "",
    base_currency: str = DEFAULT_BASE_CURRENCY,
    sale_history: UserGameSaleHistory | None = None,
    history_format: str = "duration",
    history_limit: int = 3,
) -> str:
    lines = _game_header(game)
    if prices:
        lines.append("\nPrices by region:")
        lines.extend(_card_price_lines(prices, rates, old_prices, base_currency))
        offer_end = _offer_end_line(prices)
        if offer_end:
            lines.append(f"\nOffer ends <b>{offer_end}</b>")
        lines.extend(
            format_past_sales_lines(
                sale_history,
                history_format,
                limit_per_region=history_limit,
                rates=rates,
                base_currency=base_currency,
            )
        )
    body = "\n".join(lines)
    parts = [p for p in (title, body, footer) if p]
    return "\n\n".join(parts)
