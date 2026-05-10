import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_search_results
from bot.keyboards.inline import search_results_keyboard
from bot.states.subscription import SearchForm
from services.currency import get_rates
from services.ps_store import search_games
from services.region import get_user_regions
from services.user import get_or_create_user

router = Router()


async def _do_search(message: Message, session: AsyncSession, query: str) -> None:
    user = await get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    await session.commit()

    user_regions = await get_user_regions(session, user.id)

    if not user_regions:
        games = await search_games(query)
        prices_by_game: dict[str, dict] = {}
        rates = None
    else:
        results, rates = await asyncio.gather(
            asyncio.gather(*[search_games(query, region.code) for region in user_regions]),
            get_rates(),
        )
        games = results[0]
        prices_by_game = {}
        for region, region_games in zip(user_regions, results):
            for game in region_games:
                ps_id = game["ps_id"]
                if ps_id not in prices_by_game:
                    prices_by_game[ps_id] = {}
                prices_by_game[ps_id][region.code] = (
                    game["price"], game["currency"], game["base_price"], game["discount_text"]
                )

    text = format_search_results(games, prices_by_game, has_regions=bool(user_regions), rates=rates)
    await message.answer(text, reply_markup=search_results_keyboard(games))


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    query = message.text.partition(" ")[2].strip()
    if query:
        await _do_search(message, session, query)
    else:
        await state.set_state(SearchForm.waiting_for_query)
        await message.answer("Type a game name:")


@router.message(SearchForm.waiting_for_query, ~F.text.startswith("/"))
async def on_search_query(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = message.text.strip()
    if not query:
        return
    await state.clear()
    await _do_search(message, session, query)
