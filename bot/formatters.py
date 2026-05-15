from datetime import datetime

from services.currency import PS_CURRENCY_MAP, convert_to_usd
from services.ps_store import GameResult, RegionPrice

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


def _usd_by_locale(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
) -> dict[str, float | None]:
    result = {}
    for locale, rp in prices.items():
        if rp.price is not None and rp.currency is not None and rates is not None:
            result[locale] = convert_to_usd(rp.price, rp.currency, rates)
        else:
            result[locale] = None
    return result


def _price_line(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
) -> str:
    usd_map = _usd_by_locale(prices, rates)
    cheapest = min(
        (loc for loc, usd in usd_map.items() if usd is not None),
        key=lambda loc: usd_map[loc],
        default=None,
    )

    parts = []
    for locale, rp in prices.items():
        flag = locale_flag(locale)
        if rp.price is None or rp.currency is None:
            parts.append(f"{flag} N/A")
            continue

        usd = usd_map.get(locale)
        iso = PS_CURRENCY_MAP.get(rp.currency, rp.currency)
        usd_str = f" (${usd:.2f})" if usd is not None and iso != "USD" else ""
        strike = f"<s>{_format_price(rp.base_price, rp.currency)}</s> " if rp.base_price is not None else ""
        discount_str = f" {rp.discount_text}" if rp.discount_text else ""
        price_label = f"{strike}{_format_price(rp.price, rp.currency)}{discount_str}{usd_str}"
        text = f"{flag} {price_label}"

        if locale == cheapest and cheapest is not None and len(prices) > 1:
            text = f"<b>{text}</b>"
        parts.append(text)

    return " · ".join(parts)


def _game_header(game: GameResult) -> list[str]:
    emoji = TYPE_EMOJI.get(game.type, "🎮")
    type_label = TYPE_LABEL.get(game.type, game.type) or "—"
    platforms = " · ".join(game.platforms) if game.platforms else "—"
    return [f"{emoji} {game.title}", f"{platforms} · {type_label}"]


def _card_price_lines(
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
    old_prices: dict[str, RegionPrice] | None = None,
) -> list[str]:
    usd_map = _usd_by_locale(prices, rates)
    cheapest = min(
        (loc for loc, usd in usd_map.items() if usd is not None),
        key=lambda loc: usd_map[loc],
        default=None,
    )

    lines = []
    for locale, rp in prices.items():
        flag = locale_flag(locale)
        if rp.price is None or rp.currency is None:
            lines.append(f"{flag} N/A")
            continue

        usd = usd_map.get(locale)
        iso = PS_CURRENCY_MAP.get(rp.currency, rp.currency)
        usd_str = f" (${usd:.2f})" if usd is not None and iso != "USD" else ""
        strike = f"<s>{_format_price(rp.base_price, rp.currency)}</s> " if rp.base_price is not None else ""
        discount_str = f" {rp.discount_text}" if rp.discount_text else ""
        price_label = f"{strike}{_format_price(rp.price, rp.currency)}{discount_str}{usd_str}"

        url = f"https://store.playstation.com/{locale}/product/{rp.ps_id}"
        is_cheapest = locale == cheapest and cheapest is not None and len(prices) > 1
        current = f'<a href="{url}">{price_label}</a>'
        if is_cheapest:
            current = f"<b>{current}</b>"
        text = f"{flag} {current}"

        old = (old_prices or {}).get(locale)
        if old is not None and old.price is not None and old.currency is not None and old.price != rp.price:
            old_usd = convert_to_usd(old.price, old.currency, rates) if rates else None
            old_iso = PS_CURRENCY_MAP.get(old.currency, old.currency)
            old_usd_str = f" (${old_usd:.2f})" if old_usd is not None and old_iso != "USD" else ""
            arrow = "↓" if rp.price < old.price else "↑"
            text += f"  {arrow} <s>{_format_price(old.price, old.currency)}{old_usd_str}</s>"

        lines.append(text)

    return lines


def format_game_list(
    title: str,
    footer: str,
    games: list[GameResult],
    prices_by_game: dict[str, dict[str, RegionPrice]],
    rates: dict[str, float] | None = None,
) -> str:
    if not games:
        return "Nothing found. Try a different query."

    cards = []
    for game in games:
        lines = _game_header(game)
        prices = prices_by_game.get(game.ps_id, {})
        if prices:
            lines.append(_price_line(prices, rates))
        cards.append("\n".join(lines))

    return f"{title}\n\n" + "\n\n".join(cards) + f"\n\n{footer}"


def _offer_end_line(prices: dict[str, RegionPrice]) -> str | None:
    for rp in prices.values():
        if rp.discount_end and rp.base_price is not None:
            try:
                d = datetime.strptime(rp.discount_end, "%Y-%m-%d %H:%M")
                return f"{d.day}/{d.month}/{d.year} {d.strftime('%H:%M')} UTC"
            except ValueError:
                pass
            try:
                d = datetime.strptime(rp.discount_end, "%Y-%m-%d")
                return f"{d.day}/{d.month}/{d.year} UTC"
            except (ValueError, AttributeError):
                return f"{rp.discount_end}"
    return None


def format_game_card(
    game: GameResult,
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None = None,
    old_prices: dict[str, RegionPrice] | None = None,
    title: str = "",
    footer: str = "",
) -> str:
    lines = _game_header(game)
    if prices:
        lines.append("\nPrices by region:")
        lines.extend(_card_price_lines(prices, rates, old_prices))
        offer_end = _offer_end_line(prices)
        if offer_end:
            lines.append(f"\nOffer ends:\n<b>{offer_end}</b>")
    body = "\n".join(lines)
    parts = [p for p in (title, body, footer) if p]
    return "\n\n".join(parts)
