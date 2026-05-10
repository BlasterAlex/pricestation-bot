import logging

from sqlalchemy import select

from db.models import Game, Notification, Price, Region, Subscription
from db.session import AsyncSessionFactory
from services import notifier, price, ps_store

logger = logging.getLogger(__name__)


async def check_prices() -> None:
    logger.info("Starting price check")
    async with AsyncSessionFactory() as session:
        pairs = await price.get_active_pairs(session)
        for game_id, region_id in pairs:
            await _check_pair(session, game_id, region_id)
    logger.info("Price check finished")


async def _check_pair(session, game_id: int, region_id: int) -> None:
    game = await session.get(Game, game_id)
    region = await session.get(Region, region_id)
    if not game or not region:
        return

    current_amount = await ps_store.get_game_price(game.ps_id, region.code)
    if current_amount is None:
        return

    latest = await price.get_latest_price(session, game_id, region_id)
    session.add(Price(game_id=game_id, region_id=region_id, amount=current_amount))

    if latest and current_amount < float(latest.amount):
        await _notify_subscribers(session, game_id, region_id, float(latest.amount), current_amount, region.currency, game.title)

    await session.commit()


async def _notify_subscribers(session, game_id, region_id, old_price, new_price, currency, title) -> None:
    from aiogram import Bot
    from config import settings

    result = await session.execute(
        select(Subscription).where(
            Subscription.game_id == game_id,
            Subscription.region_id == region_id,
        )
    )
    subscriptions = result.scalars().all()

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        for sub in subscriptions:
            user = await session.get(__import__("db.models", fromlist=["User"]).User, sub.user_id)
            if user and (sub.target_price is None or new_price <= float(sub.target_price)):
                await notifier.send_price_drop(bot, user.telegram_id, title, old_price, new_price, currency)
                session.add(Notification(
                    user_id=sub.user_id,
                    subscription_id=sub.id,
                    old_price=old_price,
                    new_price=new_price,
                ))
    finally:
        await bot.session.close()
