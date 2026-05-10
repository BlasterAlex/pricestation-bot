from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

_MAX_RESULTS = 20


def ps_regions_keyboard(
    countries: list[dict], tracked_locales: set[str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    count = 0
    for country in countries:
        if country["locale"] in tracked_locales:
            builder.button(text=f"✓ {country['name']}", callback_data="noop")
        else:
            builder.button(
                text=country["name"],
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
        builder.button(
            text=f"✕ {region.name}",
            callback_data=f"region_remove:{region.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cancel")
    return builder.as_markup()
