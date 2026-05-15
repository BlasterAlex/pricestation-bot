from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select

from config import settings
from db.models import GameRegion, Subscription, User
from db.session import AsyncSessionFactory
from services import notifier, price
from services.ps_store import get_game_info

logger = logging.getLogger(__name__)


async def check_prices() -> None:
    logger.info("Starting price check")
    async with AsyncSessionFactory() as session:
        game_regions = await price.get_game_regions_to_check(session)
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            for gr in game_regions:
                await _check_game_region(session, gr, bot)
        finally:
            await bot.session.close()
    logger.info("Price check finished")


async def _check_game_region(session, gr: GameRegion, bot: Bot) -> None:
    result = await get_game_info(gr.ps_id, gr.region.code)
    if result is None:
        return

    game_info, region_price = result
    if region_price is None or region_price.price is None:
        return

    new_price = region_price.price
    old_stored = float(gr.current_price) if gr.current_price is not None else None
    price_dropped = old_stored is not None and price.is_price_dropped(old_stored, new_price)

    if price_dropped:
        gr.old_price = gr.current_price
    gr.current_price = new_price
    gr.base_price = region_price.base_price
    gr.discount_text = region_price.discount_text
    gr.last_checked = datetime.now(timezone.utc)

    gr.game.title = game_info.title
    gr.game.cover_url = game_info.cover_url
    gr.game.game_type = game_info.type
    gr.game.platforms = game_info.platforms

    await session.commit()

    if price_dropped:
        await _notify_subscribers(session, gr, old_stored, new_price, bot)


async def _notify_subscribers(
    session, gr: GameRegion, old_price: float, new_price: float, bot: Bot
) -> None:
    result = await session.execute(
        select(Subscription).where(Subscription.game_id == gr.game_id)
    )
    subscriptions = result.scalars().all()

    for sub in subscriptions:
        user = await session.get(User, sub.user_id)
        if user:
            await notifier.send_price_drop(
                bot,
                user.telegram_id,
                gr.game.title,
                old_price,
                new_price,
                gr.region.currency or "",
            )
