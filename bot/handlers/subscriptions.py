from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_list
from bot.keyboards.inline import subscriptions_list_keyboard
from bot.metrics import bot_handler_errors
from bot.states.subscription import SearchForm
from services.currency import DEFAULT_BASE_CURRENCY, get_rates
from services.ps_store import GameInfo, RegionPrice
from services.subscription import get_user_subscriptions_page, subscribe_to_game, unsubscribe_from_game
from services.user import get_or_create_user

_SUBS_PAGE_SIZE = 15

router = Router()


@router.callback_query(SearchForm.showing_results, F.data.startswith("subscribe:"))
async def on_subscribe(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()

    data = await state.get_data()
    entries = data.get("entries", [])

    index = int(callback.data.split(":", 1)[1])
    if index >= len(entries):
        bot_handler_errors.inc()
        await callback.message.answer("Game not found. Please search again.")
        return

    entry = entries[index]
    game_info = GameInfo.from_dict(entry["game"])
    prices = {region: RegionPrice.from_dict(v) for region, v in entry["prices"].items()}

    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    created = await subscribe_to_game(session, user, game_info, prices)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if created:
        await callback.message.answer(
            f"🔔 Subscribed to <b>{game_info.title}</b>.\n"
            "You'll be notified when the price drops.\n\n"
            "View all subscriptions: /my_subscriptions"
        )
    else:
        await callback.message.answer(
            f"You're already subscribed to <b>{game_info.title}</b>\n\n"
            "View all subscriptions: /my_subscriptions"
        )


@router.callback_query(F.data.startswith("unsubscribe:"))
async def on_unsubscribe(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    game_id = int(callback.data.split(":", 1)[1])
    removed = await unsubscribe_from_game(session, callback.from_user.id, game_id)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if removed:
        await callback.message.answer("🔕 Unsubscribed.")
    else:
        await callback.message.answer("You're not subscribed to this game.")


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession) -> None:
    await message.answer("Search for a game first with /search, then use the Subscribe button on its card.")


async def _build_subs_page(
    session: AsyncSession,
    state: FSMContext,
    telegram_id: int,
    username: str | None,
    page: int,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Return (text, keyboard) for the given page, or None if no subscriptions."""
    user = await get_or_create_user(session, telegram_id, username)
    base_currency = user.preferred_currency or DEFAULT_BASE_CURRENCY

    total, page_items = await get_user_subscriptions_page(
        session, telegram_id, page, _SUBS_PAGE_SIZE
    )
    if total == 0:
        return None

    total_pages = (total + _SUBS_PAGE_SIZE - 1) // _SUBS_PAGE_SIZE
    games = [gi for gi, _ in page_items]
    rates = await get_rates()

    entries = [
        {
            "game": gi.to_dict(),
            "prices": {r: rp.to_dict() for r, rp in prices.items()},
        }
        for gi, prices in page_items
    ]
    await state.set_state(SearchForm.showing_results)
    await state.update_data(entries=entries, rates=rates, base_currency=base_currency)

    text = format_game_list(
        title=f"Your subscriptions ({total} total):",
        footer="Prices may be slightly outdated.",
        games=games,
        prices=[prices for _, prices in page_items],
        rates=rates,
        base_currency=base_currency,
    )
    return text, subscriptions_list_keyboard(games, page, total_pages)


@router.message(Command("my_subscriptions"))
async def cmd_my_subscriptions(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    result = await _build_subs_page(
        session, state, message.from_user.id, message.from_user.username, page=0
    )
    if result is None:
        await message.answer("You have no subscriptions yet.\nSearch for a game with /search and subscribe.")
        return
    text, keyboard = result
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("subs_page:"))
async def on_subs_page(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    page = int(callback.data.split(":", 1)[1])
    result = await _build_subs_page(
        session, state, callback.from_user.id, callback.from_user.username, page
    )
    if result is None:
        await callback.message.answer("You have no subscriptions yet.")
        return
    text, keyboard = result
    await callback.message.edit_text(text, reply_markup=keyboard)
