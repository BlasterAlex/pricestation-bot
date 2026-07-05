from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_card, format_game_list
from bot.keyboards.inline import subscriptions_list_keyboard, unsubscribe_keyboard
from bot.metrics import bot_handler_errors
from bot.states.subscription import SearchForm
from db.models import Game, GameRegion, Region, Subscription, UserRegion
from services.currency import DEFAULT_BASE_CURRENCY, get_rates
from services.price_history import LIMIT_CARD, get_user_game_sale_history, resolve_history_format
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
            "You'll be notified when the price drops.\n"
            "Price history starts from today — past sales before subscribing aren't available.\n\n"
            "View all subscriptions: /subscriptions"
        )
    else:
        await callback.message.answer(
            f"You're already subscribed to <b>{game_info.title}</b>\n\n"
            "View all subscriptions: /subscriptions"
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


async def _load_subscribed_game_card(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    game_id: int,
    *,
    history_limit: int,
    title: str = "",
) -> tuple[str, InlineKeyboardMarkup] | None:
    user = await get_or_create_user(session, telegram_id, username)
    sub = await session.scalar(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.game_id == game_id)
    )
    if sub is None:
        return None

    game = await session.scalar(select(Game).where(Game.id == game_id))
    if game is None:
        return None

    gr_stmt = (
        select(GameRegion, Region)
        .join(Region, Region.id == GameRegion.region_id)
        .join(UserRegion, UserRegion.region_id == Region.id)
        .where(GameRegion.game_id == game_id, UserRegion.user_id == user.id)
    )
    prices: dict[str, RegionPrice] = {}
    for gr, region in (await session.execute(gr_stmt)).all():
        prices[region.code] = RegionPrice(
            price=float(gr.current_price) if gr.current_price is not None else None,
            currency=region.currency,
            base_price=float(gr.base_price) if gr.base_price is not None else None,
            discount_text=gr.discount_text,
            ps_id=gr.ps_id,
            discount_end=gr.discount_end,
        )

    game_info = GameInfo(
        title=game.title,
        platforms=game.platforms or [],
        type=game.game_type,
        cover_url=game.cover_url,
        ps_id_suffix=game.ps_id_suffix,
    )
    rates = await get_rates()
    base_currency = user.preferred_currency or DEFAULT_BASE_CURRENCY
    history_format = resolve_history_format(user.history_display_format)
    sale_history = await get_user_game_sale_history(
        session, user.id, game_id, limit_per_region=history_limit,
    )

    text = format_game_card(
        game_info,
        prices,
        rates,
        title=title,
        base_currency=base_currency,
        sale_history=sale_history,
        history_format=history_format,
        history_limit=history_limit,
        show_cross_region_saves=user.show_cross_region_saves,
    )
    return text, unsubscribe_keyboard(game_id)


@router.callback_query(F.data.startswith("subs_detail:"))
async def on_subs_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    game_id = int(callback.data.split(":", 1)[1])
    result = await _load_subscribed_game_card(
        session,
        callback.from_user.id,
        callback.from_user.username,
        game_id,
        history_limit=LIMIT_CARD,
    )
    if result is None:
        await callback.message.answer("Subscription not found.")
        return

    text, keyboard = result
    await callback.message.answer(text, reply_markup=keyboard)


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
    games = [gi for _, gi, _ in page_items]
    rates = await get_rates()

    entries = [
        {
            "game": gi.to_dict(),
            "prices": {r: rp.to_dict() for r, rp in prices.items()},
        }
        for _, gi, prices in page_items
    ]
    await state.set_state(SearchForm.showing_results)
    await state.update_data(entries=entries, rates=rates, base_currency=base_currency)

    text = format_game_list(
        title=f"Your subscriptions ({total} total):",
        footer="Prices may be slightly outdated.",
        games=games,
        prices=[prices for _, _, prices in page_items],
        rates=rates,
        base_currency=base_currency,
    )
    subs_items = [(game_id, gi) for game_id, gi, _ in page_items]
    return text, subscriptions_list_keyboard(subs_items, page, total_pages)


@router.message(Command("subscriptions"))
async def cmd_subscriptions(
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
