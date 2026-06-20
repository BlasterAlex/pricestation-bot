from services.currency import DEFAULT_BASE_CURRENCY, PS_CURRENCY_MAP, PS_ISO_TO_SYMBOL, convert
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
            d = rp.discount_end
            if d.hour or d.minute:
                return f"{d.day}/{d.month}/{d.year} {d.strftime('%H:%M')} UTC"
            return f"{d.day}/{d.month}/{d.year} UTC"
    return None


def format_game_card(
    game: GameInfo,
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None = None,
    old_prices: dict[str, float] | None = None,
    title: str = "",
    footer: str = "",
    base_currency: str = DEFAULT_BASE_CURRENCY,
) -> str:
    lines = _game_header(game)
    if prices:
        lines.append("\nPrices by region:")
        lines.extend(_card_price_lines(prices, rates, old_prices, base_currency))
        offer_end = _offer_end_line(prices)
        if offer_end:
            lines.append(f"\nOffer ends:\n<b>{offer_end}</b>")
    body = "\n".join(lines)
    parts = [p for p in (title, body, footer) if p]
    return "\n\n".join(parts)
