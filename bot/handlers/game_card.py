import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_card
from services.currency import get_rates
from services.ps_store import get_game_info
from services.region import get_user_regions
from services.user import get_or_create_user

router = Router()


async def show_game_card(ps_id: str, message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.chat.id, None)
    user_regions = await get_user_regions(session, user.id)

    if not user_regions:
        await message.answer("No regions added yet.\nAdd one with /add_region")
        return

    region_results, rates = await asyncio.gather(
        asyncio.gather(*[get_game_info(ps_id, r.code) for r in user_regions]),
        get_rates(),
    )
    game = next((g for g in region_results if g is not None), None)
    prices = {
        r.code: (g.price, g.currency, g.base_price, g.discount_text)
        for r, g in zip(user_regions, region_results)
        if g is not None
    }

    if game is None:
        await message.answer("Failed to load game info.")
        return

    caption = format_game_card(
        game,
        prices,
        rates,
        footer="Want to track prices in more regions?\nAdd a new one: /add_region",
    )

    if game.cover_url:
        await message.answer_photo(photo=game.cover_url, caption=caption)
    else:
        await message.answer(caption)


@router.callback_query(F.data.startswith("game_detail:"))
async def on_game_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    ps_id = callback.data.split(":", 1)[1]
    await show_game_card(ps_id, callback.message, session)
