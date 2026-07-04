from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import locale_flag
from bot.keyboards.inline import (
    currency_suggestions_keyboard,
    settings_currency_keyboard,
    settings_history_keyboard,
    settings_main_keyboard,
    settings_regions_keyboard,
)
from bot.states.settings import SettingsForm
from services.currency import DEFAULT_BASE_CURRENCY, PS_ISO_TO_SYMBOL, find_currency_suggestions, get_rates
from services.price_history import (
    HISTORY_FORMAT_DATE,
    HISTORY_FORMAT_DURATION,
    resolve_history_format,
)
from services.region import get_user_regions
from services.user import get_or_create_user

router = Router()

POPULAR_CURRENCIES = ("USD", "EUR", "GBP", "TRY", "UAH", "PLN", "BRL", "INR")

_HISTORY_LABELS = {
    HISTORY_FORMAT_DURATION: "Duration (e.g. \"24 days ago\")",
    HISTORY_FORMAT_DATE: "Date (e.g. \"12 Mar 2026\")",
}

_HISTORY_SHORT = {
    HISTORY_FORMAT_DURATION: "Duration",
    HISTORY_FORMAT_DATE: "Date",
}


def _currency_label(iso: str) -> str:
    symbol = PS_ISO_TO_SYMBOL.get(iso, iso)
    return f"{iso} ({symbol})" if symbol != iso else iso


def _format_tracked_regions(regions) -> str:
    if not regions:
        return "none — add at least one to search or subscribe"
    return "\n".join(f"• {locale_flag(r.code)} {r.name}" for r in regions)


async def _build_settings_text(session: AsyncSession, user) -> str:
    regions = await get_user_regions(session, user.id)
    currency = user.preferred_currency or DEFAULT_BASE_CURRENCY
    history = resolve_history_format(user.history_display_format)
    regions_block = _format_tracked_regions(regions)

    return (
        "⚙️ <b>Settings</b>\n\n"
        f"<b>Display currency:</b> {_currency_label(currency)}\n"
        f"<b>Sale history format:</b> {_HISTORY_SHORT[history]}\n"
        f"\n<b>Tracked regions</b>:\n{regions_block}"
    )


async def _show_settings(message: Message, session: AsyncSession, user) -> None:
    text = await _build_settings_text(session, user)
    await message.answer(text, reply_markup=settings_main_keyboard())


async def _edit_settings(callback: CallbackQuery, session: AsyncSession, user) -> None:
    text = await _build_settings_text(session, user)
    await callback.message.edit_text(text, reply_markup=settings_main_keyboard())


async def _set_currency(iso: str, user, session: AsyncSession) -> None:
    user.preferred_currency = iso
    await session.commit()


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    await _show_settings(message, session, user)


@router.callback_query(F.data == "settings:show")
async def on_settings_show(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    await _edit_settings(callback, session, user)
    await callback.answer()


@router.callback_query(F.data == "settings:currency")
async def on_settings_currency_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    rates = await get_rates()
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    current = user.preferred_currency or DEFAULT_BASE_CURRENCY
    await callback.message.edit_text(
        f"Select display currency.\nCurrent: <b>{_currency_label(current)}</b>",
        reply_markup=settings_currency_keyboard(rates, POPULAR_CURRENCIES),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:currency:custom")
async def on_settings_currency_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.waiting_for_currency)
    await callback.message.edit_text(
        "Send a 3-letter ISO 4217 currency code (e.g. <code>EUR</code>, <code>SGD</code>)."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:currency:"))
async def on_settings_currency_set(callback: CallbackQuery, session: AsyncSession) -> None:
    iso = callback.data.split(":", 2)[2]
    if iso == "custom":
        return

    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    await _set_currency(iso, user, session)
    await _edit_settings(callback, session, user)
    await callback.answer(f"Currency set to {iso}")


@router.message(SettingsForm.waiting_for_currency, ~F.text.startswith("/"))
async def on_settings_currency_input(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    arg = message.text.strip().upper()
    if not arg:
        return

    rates = await get_rates()
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    if arg in rates or arg == "USD":
        await _set_currency(arg, user, session)
        await state.clear()
        await _show_settings(message, session, user)
        return

    suggestions = find_currency_suggestions(arg, rates)
    if not suggestions:
        await message.answer(
            f"<b>{arg}</b> is not a recognised currency code.\n"
            "Try a valid ISO 4217 code like EUR, GBP, SGD."
        )
        return

    await message.answer(
        f"<b>{arg}</b> not found. Did you mean:",
        reply_markup=currency_suggestions_keyboard(suggestions),
    )


@router.callback_query(F.data.startswith("currency_select:"))
async def on_currency_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    iso = callback.data.split(":", 1)[1]
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    await _set_currency(iso, user, session)
    await state.clear()
    await _edit_settings(callback, session, user)
    await callback.answer(f"Currency set to {iso}")


@router.callback_query(F.data == "settings:history")
async def on_settings_history_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    current = resolve_history_format(user.history_display_format)
    await callback.message.edit_text(
        f"Sale history date format.\nCurrent: <b>{_HISTORY_LABELS[current]}</b>",
        reply_markup=settings_history_keyboard(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:history:"))
async def on_settings_history_set(callback: CallbackQuery, session: AsyncSession) -> None:
    mode = callback.data.split(":", 2)[2]
    if mode not in (HISTORY_FORMAT_DURATION, HISTORY_FORMAT_DATE):
        await callback.answer("Invalid format.")
        return

    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    user.history_display_format = mode
    await session.commit()
    await _edit_settings(callback, session, user)
    await callback.answer()


@router.callback_query(F.data == "settings:regions")
async def on_settings_regions(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    regions = await get_user_regions(session, user.id)
    if not regions:
        text = "You have no tracked regions yet.\nAdd one to search games and track prices."
    else:
        text = "Your regions (tap ✕ to remove):"
    await callback.message.edit_text(text, reply_markup=settings_regions_keyboard(regions))
    await callback.answer()
