from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.currency import DEFAULT_BASE_CURRENCY, PS_ISO_TO_SYMBOL, get_rates
from services.user import get_or_create_user

router = Router()

_POPULAR = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "BRL", "PLN", "TRY", "UAH"]


@router.message(Command("currency"))
async def cmd_currency(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    arg = message.text.partition(" ")[2].strip().upper()

    if not arg:
        current = user.preferred_currency or DEFAULT_BASE_CURRENCY
        symbol = PS_ISO_TO_SYMBOL.get(current, current)
        popular = " · ".join(
            f"{c} ({PS_ISO_TO_SYMBOL.get(c, c)})" for c in _POPULAR
        )
        await message.answer(
            f"Your current display currency: <b>{current} ({symbol})</b>\n\n"
            f"To change it, use:\n<code>/currency EUR</code>\n\n"
            f"Popular choices:\n{popular}\n\n"
            f"Any ISO 4217 currency code is accepted (e.g. SGD, HKD, MYR)."
        )
        return

    rates = await get_rates()
    if arg != "USD" and arg not in rates:
        await message.answer(
            f"<b>{arg}</b> is not a recognised currency code.\n"
            "Use a valid ISO 4217 code like EUR, GBP, SGD, HKD, etc."
        )
        return

    user.preferred_currency = arg
    await session.commit()

    symbol = PS_ISO_TO_SYMBOL.get(arg, arg)
    await message.answer(f"Display currency set to <b>{arg} ({symbol})</b>.")
