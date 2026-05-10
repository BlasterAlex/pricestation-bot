from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.formatters import TYPE_EMOJI, locale_flag

_MAX_RESULTS = 20


def ps_regions_keyboard(
    countries: list[dict], tracked_locales: set[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    count = 0
    for country in countries:
        flag = locale_flag(country["locale"])
        if country["locale"] in tracked_locales:
            builder.button(text=f"✓ {flag} {country['name']}", callback_data="noop")
        else:
            builder.button(
                text=f"{flag} {country['name']}",
                callback_data=f"region_add:{country['locale']}",
            )
        count += 1
        if count >= _MAX_RESULTS:
            break
    builder.adjust(2)
    return builder.as_markup()


def user_regions_keyboard(regions: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        flag = locale_flag(region.code)
        builder.button(
            text=f"✕ {flag} {region.name}",
            callback_data=f"region_remove:{region.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def search_results_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game in games:
        emoji = TYPE_EMOJI.get(game["type"], "🎮")
        builder.button(
            text=f"{emoji} {game['title']}",
            callback_data=f"subscribe:{game['ps_id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cancel")
    return builder.as_markup()
