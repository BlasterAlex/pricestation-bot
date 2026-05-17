from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.metrics import bot_handler_errors
from bot.states.subscription import SearchForm
from services.ps_store import GameInfo, RegionPrice
from services.subscription import subscribe_to_game, unsubscribe_from_game
from services.user import get_or_create_user

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

    if created:
        await callback.message.answer(
            f"🔔 Subscribed to <b>{game_info.title}</b>.\n"
            "You'll be notified when the price drops."
        )
    else:
        await callback.message.answer(
            f"You're already subscribed to <b>{game_info.title}</b> 🔔"
        )


@router.callback_query(SearchForm.showing_results, F.data.startswith("unsubscribe:"))
async def on_unsubscribe(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()

    data = await state.get_data()
    entries = data.get("entries", [])

    index = int(callback.data.split(":", 1)[1])
    if index >= len(entries):
        bot_handler_errors.inc()
        await callback.message.answer("Game not found. Please search again.")
        return

    game_info = GameInfo.from_dict(entries[index]["game"])
    removed = await unsubscribe_from_game(session, callback.from_user.id, game_info.normalized_title)

    if removed:
        await callback.message.answer(f"🔕 Unsubscribed from <b>{game_info.title}</b>.")
    else:
        await callback.message.answer(f"You're not subscribed to <b>{game_info.title}</b>.")


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession) -> None:
    await message.answer("Search for a game first with /search, then use the Subscribe button on its card.")


@router.message(Command("my"))
async def cmd_my_subscriptions(message: Message, session: AsyncSession) -> None:
    await message.answer("Your subscriptions:")
