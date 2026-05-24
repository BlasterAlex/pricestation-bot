from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot

from db.session import AsyncSessionFactory
from services import price
from services.currency import get_rates
from services.notifier import notify_price_drop
from services.ps_store import GameInfo, RegionPrice
from worker.metrics import notifications_failed, notifications_sent

logger = logging.getLogger(__name__)


async def send_notifications(bot: Bot) -> None:
    logger.info("Starting notification job")
    async with AsyncSessionFactory() as session:
        drops = await price.get_pending_drops(session)

        if not drops:
            logger.info("No pending price drops to notify")
            return

        rates = await get_rates()
        sent_total = 0

        for drop in drops:
            game = drop.game
            gr_by_code = {gr.region.code: gr for gr in game.game_regions}

            game_info = GameInfo(
                title=game.title,
                platforms=game.platforms or [],
                type=game.game_type,
                cover_url=game.cover_url,
                ps_id_suffix=game.ps_id_suffix,
            )

            sent_for_drop = 0
            for sub in game.subscriptions:
                user = sub.user
                user_region_codes = {r.code for r in user.regions}

                prices: dict[str, RegionPrice] = {}
                old_prices: dict[str, float] = {}

                for code, gr in gr_by_code.items():
                    # Only show regions the user actually tracks
                    if code not in user_region_codes:
                        continue
                    if gr.current_price is None:
                        continue

                    currency = gr.region.currency
                    discount_end_str = (
                        gr.discount_end.strftime("%Y-%m-%d %H:%M") if gr.discount_end else None
                    )

                    prices[code] = RegionPrice(
                        price=float(gr.current_price),
                        currency=currency,
                        base_price=float(gr.base_price) if gr.base_price is not None else None,
                        discount_text=gr.discount_text,
                        ps_id=gr.ps_id,
                        discount_end=discount_end_str,
                    )

                    if gr.old_price is not None:
                        old_prices[code] = float(gr.old_price)

                if not prices:
                    continue

                try:
                    await notify_price_drop(
                        bot=bot,
                        telegram_id=user.telegram_id,
                        game_id=game.id,
                        game_info=game_info,
                        prices=prices,
                        old_prices=old_prices or None,
                        rates=rates,
                    )
                    sent_for_drop += 1
                except Exception:
                    logger.exception(
                        "Failed to notify telegram_id=%d game_id=%d",
                        user.telegram_id, game.id,
                    )
                    notifications_failed.inc()

            # Mark as notified regardless of per-user failures to avoid duplicate notifications
            drop.notified_at = datetime.now(timezone.utc)
            sent_total += sent_for_drop
            logger.info(
                "Notified %d user(s) for game_id=%d %r",
                sent_for_drop, game.id, game.title,
            )

        await session.commit()
        notifications_sent.inc(sent_total)
    logger.info("Notification job finished: sent=%d", sent_total)
