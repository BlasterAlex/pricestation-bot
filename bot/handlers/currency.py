from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import currency_suggestions_keyboard
from services.currency import DEFAULT_BASE_CURRENCY, PS_ISO_TO_SYMBOL, find_currency_suggestions, get_rates
from services.user import get_or_create_user

router = Router()


def _currency_label(iso: str) -> str:
    symbol = PS_ISO_TO_SYMBOL.get(iso, iso)
    return f"{iso} ({symbol})" if symbol != iso else iso


async def _set_currency(iso: str, user, session: AsyncSession) -> str:
    user.preferred_currency = iso
    await session.commit()
    return f"Display currency set to <b>{_currency_label(iso)}</b>."


@router.message(Command("currency"))
async def cmd_currency(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    arg = message.text.partition(" ")[2].strip().upper()

    if not arg:
        current = user.preferred_currency or DEFAULT_BASE_CURRENCY
        await message.answer(
            f"Your current display currency: <b>{_currency_label(current)}</b>\n\n"
            f"To change it, use:\n<code>/currency EUR</code>\n\n"
            f"Any ISO 4217 currency code is accepted (e.g. SGD, HKD, MYR)."
        )
        return

    rates = await get_rates()

    if arg in rates or arg == "USD":
        await message.answer(await _set_currency(arg, user, session))
        return

    suggestions = find_currency_suggestions(arg, rates)
    if not suggestions:
        await message.answer(
            f"<b>{arg}</b> is not a recognised currency code and no similar codes were found.\n"
            "Use a valid ISO 4217 code like EUR, GBP, SGD, HKD, etc."
        )
        return

    await message.answer(
        f"<b>{arg}</b> not found. Did you mean:",
        reply_markup=currency_suggestions_keyboard(suggestions),
    )


@router.callback_query(F.data.startswith("currency_select:"))
async def on_currency_select(callback: CallbackQuery, session: AsyncSession) -> None:
    iso = callback.data.split(":", 1)[1]
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    text = await _set_currency(iso, user, session)
    await callback.message.edit_text(text)
    await callback.answer()
