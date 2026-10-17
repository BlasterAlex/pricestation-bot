from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()

ISSUES_URL = "https://github.com/BlasterAlex/pricestation-bot/issues"

_ABOUT = (
    "<b>About</b>\n\n"
    "PriceStation tracks PS Store prices and notifies you when they drop.\n\n"
    f'Bugs and ideas go to <a href="{ISSUES_URL}">GitHub Issues</a>.'
)

_ABOUT_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="Open Issues", url=ISSUES_URL)]]
)


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(_ABOUT, reply_markup=_ABOUT_KEYBOARD)
