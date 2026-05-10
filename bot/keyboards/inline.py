from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def regions_keyboard(regions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.button(
            text=region["name"],
            callback_data=f"region:{region['code']}",
        )
    builder.adjust(2)
    return builder.as_markup()
