from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from db.models import GameRegion, PriceDrop
from db.session import AsyncSessionFactory
from services import price
from services.ps_store import get_game_info
from worker.metrics import (
    price_check_duration,
    price_check_last_run,
    price_check_regions,
    price_check_runs,
    price_drops_created,
)

logger = logging.getLogger(__name__)


async def check_prices() -> None:
    logger.info("Starting price check")
    price_check_runs.inc()
    t0 = time.monotonic()

    async with AsyncSessionFactory() as session:
        game_regions = await price.get_game_regions_to_check(session)
        unique_games = len({gr.game_id for gr in game_regions})
        logger.info("%d games, %d store pages to check", unique_games, len(game_regions))
        skipped = dropped = unchanged = 0
        for gr in game_regions:
            result = await _check_game_region(session, gr)
            if result == "skipped":
                skipped += 1
            elif result == "dropped":
                dropped += 1
            else:
                unchanged += 1

    price_check_regions.labels(result="dropped").inc(dropped)
    price_check_regions.labels(result="unchanged").inc(unchanged)
    price_check_regions.labels(result="skipped").inc(skipped)
    price_check_duration.observe(time.monotonic() - t0)
    price_check_last_run.set(time.time())

    logger.info(
        "Price check finished: checked=%d dropped=%d unchanged=%d skipped=%d",
        len(game_regions), dropped, unchanged, skipped,
    )


async def _check_game_region(session, gr: GameRegion) -> str:
    result = await get_game_info(gr.ps_id, gr.region.code)
    if result is None:
        logger.warning("no data from PS Store ps_id=%s region=%s", gr.ps_id, gr.region.code)
        return "skipped"

    game_info, region_price = result
    if region_price is None or region_price.price is None:
        logger.warning("no price ps_id=%s region=%s", gr.ps_id, gr.region.code)
        return "skipped"

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

    if price_dropped:
        await session.execute(
            insert(PriceDrop)
            .values(game_id=gr.game_id)
            .on_conflict_do_nothing(
                index_elements=["game_id"],
                index_where=text("notified_at IS NULL"),
            )
        )
        price_drops_created.inc()
        logger.info("price drop game_id=%d %s %.2f -> %.2f", gr.game_id, gr.region.code, old_stored, new_price)

    await session.commit()
    return "dropped" if price_dropped else "unchanged"
