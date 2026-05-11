from services.currency import PS_CURRENCY_MAP, convert_to_usd
from services.ps_store import GameResult

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
    prices: dict[str, tuple],
    rates: dict[str, float] | None,
) -> dict[str, float | None]:
    result = {}
    for locale, price_tuple in prices.items():
        amount, currency = price_tuple[0], price_tuple[1]
        if amount is not None and currency is not None and rates is not None:
            result[locale] = convert_to_usd(amount, currency, rates)
        else:
            result[locale] = None
    return result


def _price_line(
    prices: dict[str, tuple],
    rates: dict[str, float] | None,
    *,
    with_link: bool = False,
    ps_id: str = "",
) -> str:
    usd_map = _usd_by_locale(prices, rates)
    cheapest = min(
        (loc for loc, usd in usd_map.items() if usd is not None),
        key=lambda loc: usd_map[loc],
        default=None,
    )

    parts = []
    for locale, price_tuple in prices.items():
        amount, currency, base_price, discount_text = price_tuple[:4]
        flag = locale_flag(locale)
        if amount is None or currency is None:
            parts.append(f"{flag} N/A")
            continue

        usd = usd_map.get(locale)
        iso = PS_CURRENCY_MAP.get(currency, currency)
        usd_str = f" (${usd:.2f})" if usd is not None and iso != "USD" else ""
        strike = f"<s>{_format_price(base_price, currency)}</s> " if base_price is not None else ""
        discount_str = f" {discount_text}" if discount_text else ""
        price_label = f"{strike}{_format_price(amount, currency)}{discount_str}{usd_str}"

        if with_link and ps_id:
            url = f"https://store.playstation.com/{locale}/product/{ps_id}"
            text = f'{flag} <a href="{url}">{price_label}</a>'
        else:
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
    ps_id: str,
    prices: dict[str, tuple],
    rates: dict[str, float] | None,
    old_prices: dict[str, tuple] | None = None,
) -> list[str]:
    usd_map = _usd_by_locale(prices, rates)
    cheapest = min(
        (loc for loc, usd in usd_map.items() if usd is not None),
        key=lambda loc: usd_map[loc],
        default=None,
    )

    lines = []
    for locale, price_tuple in prices.items():
        amount, currency, base_price, discount_text = price_tuple[:4]
        flag = locale_flag(locale)
        if amount is None or currency is None:
            lines.append(f"{flag} N/A")
            continue

        usd = usd_map.get(locale)
        iso = PS_CURRENCY_MAP.get(currency, currency)
        usd_str = f" (${usd:.2f})" if usd is not None and iso != "USD" else ""
        strike = f"<s>{_format_price(base_price, currency)}</s> " if base_price is not None else ""
        discount_str = f" {discount_text}" if discount_text else ""
        price_label = f"{strike}{_format_price(amount, currency)}{discount_str}{usd_str}"

        url = f"https://store.playstation.com/{locale}/product/{ps_id}"
        is_cheapest = locale == cheapest and cheapest is not None and len(prices) > 1
        current = f'<a href="{url}">{price_label}</a>'
        if is_cheapest:
            current = f"<b>{current}</b>"
        text = f"{flag} {current}"

        old = (old_prices or {}).get(locale)
        if old is not None:
            old_amount, old_currency = old[0], old[1]
            if old_amount is not None and old_currency is not None and old_amount != amount:
                old_usd = convert_to_usd(old_amount, old_currency, rates) if rates else None
                old_iso = PS_CURRENCY_MAP.get(old_currency, old_currency)
                old_usd_str = f" (${old_usd:.2f})" if old_usd is not None and old_iso != "USD" else ""
                arrow = "↓" if amount < old_amount else "↑"
                text += f"  {arrow} <s>{_format_price(old_amount, old_currency)}{old_usd_str}</s>"

        lines.append(text)

    return lines


def format_game_list(
    title: str,
    footer: str,
    games: list[GameResult],
    prices_by_game: dict[str, dict[str, tuple]],
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


def format_game_card(
    game: GameResult,
    prices: dict[str, tuple],
    rates: dict[str, float] | None = None,
    old_prices: dict[str, tuple] | None = None,
    title: str = "",
    footer: str = "",
) -> str:
    lines = _game_header(game)
    if prices:
        lines.append("\nPrices by region:")
        lines.extend(_card_price_lines(game.ps_id, prices, rates, old_prices))
    body = "\n".join(lines)
    parts = [p for p in (title, body, footer) if p]
    return "\n\n".join(parts)
