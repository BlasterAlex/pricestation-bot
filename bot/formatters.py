from services.currency import PS_CURRENCY_MAP, convert_to_usd

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


def _game_card(
    game: dict,
    prices: dict[str, tuple[float | None, str | None, float | None, str | None]],
    rates: dict[str, float] | None = None,
) -> str:
    emoji = TYPE_EMOJI.get(game["type"], "🎮")
    type_label = TYPE_LABEL.get(game["type"], game["type"])
    platforms = " · ".join(game["platforms"]) if game["platforms"] else "—"

    lines = [
        f"{emoji} {game['title']}",
        f"{platforms} · {type_label}",
    ]

    if prices:
        usd_by_locale: dict[str, float | None] = {}
        for locale, (amount, currency, *_) in prices.items():
            if amount is not None and currency is not None and rates is not None:
                usd_by_locale[locale] = convert_to_usd(amount, currency, rates)
            else:
                usd_by_locale[locale] = None

        cheapest = min(
            (loc for loc, usd in usd_by_locale.items() if usd is not None),
            key=lambda loc: usd_by_locale[loc],
            default=None,
        )

        ps_id = game["ps_id"]
        price_parts = []
        for locale, (amount, currency, base_price, discount_text) in prices.items():
            flag = locale_flag(locale)
            if amount is None or currency is None:
                price_parts.append(f"{flag} N/A")
                continue

            usd = usd_by_locale.get(locale)
            usd_str = f" (${usd:.2f})" if usd is not None and PS_CURRENCY_MAP.get(currency) != "USD" else ""

            strike = f"<s>{_format_price(base_price, currency)}</s> " if base_price is not None else ""
            discount_str = f" {discount_text}" if discount_text else ""

            url = f"https://store.playstation.com/{locale}/product/{ps_id}"
            price_label = f"{strike}{_format_price(amount, currency)}{discount_str}{usd_str}"
            text = f'{flag} <a href="{url}">{price_label}</a>'

            if locale == cheapest and cheapest is not None and len(prices) > 1:
                text = f"<b>{text}</b>"

            price_parts.append(text)

        lines.append(" · ".join(price_parts))

    return "\n".join(lines)


def format_search_results(
    games: list[dict],
    prices_by_game: dict[str, dict[str, tuple[float | None, str | None]]],
    has_regions: bool,
    rates: dict[str, float] | None = None,
) -> str:
    if not games:
        return "Nothing found. Try a different query."

    cards = [
        _game_card(game, prices_by_game.get(game["ps_id"], {}), rates)
        for game in games
    ]
    text = "\n\n".join(cards)

    if not has_regions:
        footer = "No regions added yet.\nAdd one with /add_region"
    else:
        footer = "Want to track prices in more regions?\nAdd a new one: /add_region"

    return f"Select games to subscribe to:\n\n{text}\n\n{footer}"
