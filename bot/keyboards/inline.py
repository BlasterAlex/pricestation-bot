from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.formatters import TYPE_EMOJI, locale_flag
from services.ps_store import GameInfo


def _choice_button(
    builder: InlineKeyboardBuilder,
    label: str,
    callback_data: str,
    *,
    selected: bool,
) -> None:
    """Selected option gets a checkmark and noop (Telegram has no disabled inline buttons)."""
    builder.button(
        text=f"✓ {label}" if selected else label,
        callback_data="noop" if selected else callback_data,
    )


def ps_regions_keyboard(
    countries: list[dict], tracked_locales: set[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for country in countries:
        flag = locale_flag(country["locale"])
        label = f"{flag} {country['name']}"
        _choice_button(
            builder,
            label,
            f"region_add:{country['locale']}",
            selected=country["locale"] in tracked_locales,
        )
    builder.adjust(2)
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


def price_drop_keyboard(game_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Details", callback_data=f"subs_detail:{game_id}")
    builder.button(text="🔕 Unsubscribe", callback_data=f"unsubscribe:{game_id}")
    builder.adjust(1)
    return builder.as_markup()


def subscriptions_list_keyboard(
    items: list[tuple[int, GameInfo]], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_id, game in items:
        emoji = TYPE_EMOJI.get(game.type, "🎮")
        builder.button(text=f"{emoji} {game.title}", callback_data=f"subs_detail:{game_id}")
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


def settings_main_keyboard(
    *,
    show_cross_region: bool = False,
    cross_region_enabled: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💱 Change currency", callback_data="settings:currency")
    builder.button(text="📅 History format", callback_data="settings:history")
    if show_cross_region:
        label = "Hide save compatible" if cross_region_enabled else "Show save compatible"
        builder.button(
            text=f"💾 {label}",
            callback_data="settings:cross_region:toggle",
        )
    builder.button(text="🌍 Manage regions", callback_data="settings:regions")
    builder.adjust(1)
    return builder.as_markup()


def settings_currency_keyboard(
    rates: dict[str, float], popular: tuple[str, ...]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for iso in popular:
        if iso == "USD" or iso in rates:
            builder.button(text=iso, callback_data=f"settings:currency:{iso}")
    builder.adjust(4)
    builder.row(InlineKeyboardButton(text="Enter code…", callback_data="settings:currency:custom"))
    builder.row(InlineKeyboardButton(text="← Back", callback_data="settings:show"))
    return builder.as_markup()


def settings_history_keyboard(current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _choice_button(builder, "Duration", "settings:history:duration", selected=current == "duration")
    _choice_button(builder, "Date", "settings:history:date", selected=current == "date")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Back", callback_data="settings:show"))
    return builder.as_markup()


def settings_regions_keyboard(regions: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        flag = locale_flag(region.code)
        builder.button(
            text=f"✕ {flag} {region.name}",
            callback_data=f"region_remove:{region.id}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="➕ Add region", callback_data="settings:regions:add"))
    builder.row(InlineKeyboardButton(text="← Back", callback_data="settings:show"))
    return builder.as_markup()


def currency_suggestions_keyboard(suggestions: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for iso, name in suggestions:
        builder.button(text=f"{iso} — {name}", callback_data=f"currency_select:{iso}")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cancel")
    return builder.as_markup()
