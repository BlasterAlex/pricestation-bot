from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.formatters import TYPE_EMOJI, locale_flag
from services.ps_store import GameInfo


def ps_regions_keyboard(
    countries: list[dict], tracked_locales: set[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for country in countries:
        flag = locale_flag(country["locale"])
        if country["locale"] in tracked_locales:
            builder.button(text=f"✓ {flag} {country['name']}", callback_data="noop")
        else:
            builder.button(
                text=f"{flag} {country['name']}",
                callback_data=f"region_add:{country['locale']}",
            )
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


def _add_game_buttons(builder: InlineKeyboardBuilder, games: list[GameInfo]) -> None:
    for i, game in enumerate(games):
        emoji = TYPE_EMOJI.get(game.type, "🎮")
        builder.button(text=f"{emoji} {game.title}", callback_data=f"game_select:{i}")


def search_results_keyboard(games: list[GameInfo]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _add_game_buttons(builder, games)
    builder.adjust(1)
    return builder.as_markup()


def subscribe_keyboard(game_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 Subscribe", callback_data=f"subscribe:{game_index}")
    return builder.as_markup()


def unsubscribe_keyboard(game_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔕 Unsubscribe", callback_data=f"unsubscribe:{game_id}")
    return builder.as_markup()


def subscriptions_list_keyboard(
    games: list[GameInfo], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _add_game_buttons(builder, games)
    builder.adjust(1)
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="← Prev", callback_data=f"subs_page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="Next →", callback_data=f"subs_page:{page + 1}"))
        builder.row(*nav)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cancel")
    return builder.as_markup()
