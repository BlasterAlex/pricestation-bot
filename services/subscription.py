import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bot.metrics import region_sync_not_found, subscriptions_already_exists, subscriptions_created
from db.models.game import Game
from db.models.game_region import GameRegion
from db.models.region import Region
from db.models.subscription import Subscription
from db.models.user import User
from services.ps_store import GameInfo, RegionPrice, best_ps_id, get_game_info, search_games

logger = logging.getLogger(__name__)


def _parse_discount_end(s: str | None) -> datetime | None:
    if s is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _make_game_region(game_id: int, region_id: int, rp: RegionPrice) -> GameRegion:
    return GameRegion(
        game_id=game_id,
        region_id=region_id,
        ps_id=rp.ps_id,
        current_price=rp.price,
        base_price=rp.base_price,
        discount_text=rp.discount_text,
        discount_end=_parse_discount_end(rp.discount_end),
    )


async def subscribe_to_game(
    session: AsyncSession,
    user: User,
    game_info: GameInfo,
    prices: dict[str, RegionPrice],
) -> bool:
    """
    Ensure the game and its game_regions exist in the DB, then create a subscription.
    Returns True if a new subscription was created, False if it already existed.
    """
    normalized = game_info.normalized_title
    region_codes = list(prices.keys())

    # Single query: game + its game_regions (with region) + subscription for this user
    stmt = (
        select(Game, GameRegion, Region, Subscription)
        .outerjoin(GameRegion, GameRegion.game_id == Game.id)
        .outerjoin(Region, Region.id == GameRegion.region_id)
        .outerjoin(
            Subscription,
            (Subscription.game_id == Game.id) & (Subscription.user_id == user.id),
        )
        .where(Game.normalized_title == normalized)
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        # Game doesn't exist yet — create game, game_regions, and subscription
        game = Game(
            title=game_info.title,
            normalized_title=normalized,
            cover_url=game_info.cover_url,
            game_type=game_info.type,
            platforms=game_info.platforms,
        )
        session.add(game)
        await session.flush()

        regions_result = await session.execute(
            select(Region).where(Region.code.in_(region_codes))
        )
        regions_by_code = {r.code: r for r in regions_result.scalars()}

        for code, rp in prices.items():
            region = regions_by_code.get(code)
            if region is None:
                continue
            if region.currency is None and rp.currency is not None:
                region.currency = rp.currency
            session.add(_make_game_region(game.id, region.id, rp))

        session.add(Subscription(user_id=user.id, game_id=game.id))
        await session.commit()
        logger.info(
            "subscribed telegram_id=%d to new game %r regions=%s",
            user.telegram_id, game_info.title, region_codes,
        )
        subscriptions_created.inc()
        return True

    # Game already exists
    game: Game = rows[0][0]
    existing_sub: Subscription | None = rows[0][3]

    if existing_sub is not None:
        subscriptions_already_exists.inc()
        return False

    # Prefer ASCII title (same rule as in search merge: localized prefixes like "Набір" lose to ASCII)
    if game_info.title.isascii() and not game.title.isascii():
        logger.info("updating title for game_id=%d: %r -> %r", game.id, game.title, game_info.title)
        game.title = game_info.title

    # Build map of existing game_regions and regions by code
    existing_grs: dict[str, GameRegion] = {}
    existing_regions: dict[str, Region] = {}
    for _, gr, region, _ in rows:
        if gr is not None and region is not None:
            existing_grs[region.code] = gr
            existing_regions[region.code] = region

    # Fetch regions needed for any missing game_regions
    missing_codes = [c for c in region_codes if c not in existing_grs]
    regions_by_code: dict[str, Region] = {}
    if missing_codes:
        regions_result = await session.execute(
            select(Region).where(Region.code.in_(missing_codes))
        )
        regions_by_code = {r.code: r for r in regions_result.scalars()}

    for code, rp in prices.items():
        region = existing_regions.get(code) or regions_by_code.get(code)
        if region is not None and region.currency is None and rp.currency is not None:
            region.currency = rp.currency
        if code in existing_grs:
            gr = existing_grs[code]
            if gr.ps_id != rp.ps_id:
                logger.warning(
                    "ps_id mismatch for %r in %s: db=%s current=%s",
                    game.title, code, gr.ps_id, rp.ps_id,
                )
        else:
            region = regions_by_code.get(code)
            if region is None:
                continue
            logger.info("adding game_region game_id=%d region=%s ps_id=%s", game.id, code, rp.ps_id)
            session.add(_make_game_region(game.id, region.id, rp))

    session.add(Subscription(user_id=user.id, game_id=game.id))
    await session.commit()
    logger.info(
        "subscribed telegram_id=%d to existing game_id=%d %r",
        user.telegram_id, game.id, game.title,
    )
    subscriptions_created.inc()
    return True


async def is_subscribed(session: AsyncSession, telegram_id: int, normalized_title: str) -> bool:
    stmt = (
        select(Subscription.id)
        .join(Game, Game.id == Subscription.game_id)
        .join(User, User.id == Subscription.user_id)
        .where(Game.normalized_title == normalized_title)
        .where(User.telegram_id == telegram_id)
    )
    return (await session.scalar(stmt)) is not None


async def unsubscribe_from_game(
    session: AsyncSession,
    telegram_id: int,
    normalized_title: str,
) -> bool:
    """Delete subscription. Returns True if it existed, False otherwise."""
    stmt = (
        select(Subscription)
        .join(Game, Game.id == Subscription.game_id)
        .join(User, User.id == Subscription.user_id)
        .where(Game.normalized_title == normalized_title)
        .where(User.telegram_id == telegram_id)
    )
    sub = await session.scalar(stmt)
    if sub is None:
        return False
    await session.delete(sub)
    await session.commit()
    logger.info("unsubscribed telegram_id=%d from %r", telegram_id, normalized_title)
    return True


async def _find_region_price(
    title: str,
    normalized_title: str,
    region_code: str,
) -> RegionPrice | None:
    """Search PS Store by title and return the RegionPrice for the matching game.

    Fetches the top 5 results for `title` in `region_code` and returns the price
    for the first result whose normalized title exactly matches `normalized_title`.
    Returns None if no match is found (game unavailable or title mismatch).
    """
    results = await search_games(title, region_code, page_size=5)
    return next((rp for g, rp in results if g.normalized_title == normalized_title), None)


async def sync_subscriptions_for_new_region(
    session: AsyncSession,
    user: User,
    region: Region,
) -> None:
    """Create game_regions for a newly added region for all games the user is already subscribed to."""
    # Games subscribed by user that have no game_region for the new region yet,
    # with an available ps_id from any existing game_region.
    existing_gr = aliased(GameRegion)
    stmt = (
        select(Game.id, Game.title, Game.normalized_title, Region.code, GameRegion.ps_id)
        .join(Subscription, (Subscription.game_id == Game.id) & (Subscription.user_id == user.id))
        .join(GameRegion, GameRegion.game_id == Game.id)
        .join(Region, Region.id == GameRegion.region_id)
        .where(GameRegion.ps_id.is_not(None))
        .where(
            ~exists().where(
                (existing_gr.game_id == Game.id) & (existing_gr.region_id == region.id)
            )
        )
    )
    rows = (await session.execute(stmt)).all()

    # Collect all ps_ids per game keyed by their region code, then pick the best one.
    # Fall back to title search for games where no matching prefix ps_id is found.
    game_meta: dict[int, tuple[str, str]] = {}  # game_id -> (title, normalized_title)
    game_ps_ids_by_region: dict[int, dict[str, str]] = {}
    for game_id, title, normalized_title, region_code, ps_id in rows:
        game_meta[game_id] = (title, normalized_title)
        game_ps_ids_by_region.setdefault(game_id, {})[region_code] = ps_id

    if not game_ps_ids_by_region:
        logger.info(
            "sync: all game_regions already exist for region=%s telegram_id=%d",
            region.code, user.telegram_id,
        )
        return

    chosen: dict[int, str] = {}       # game_id -> ps_id, resolved via get_game_info
    to_search: list[tuple[int, str, str]] = []  # (game_id, title, normalized_title)

    for game_id, ps_ids in game_ps_ids_by_region.items():
        pid = best_ps_id(region.code, ps_ids)
        if pid:
            chosen[game_id] = pid
        else:
            to_search.append((game_id, *game_meta[game_id]))

    info_results, search_results = await asyncio.gather(
        asyncio.gather(*[get_game_info(ps_id, region.code) for ps_id in chosen.values()]),
        asyncio.gather(*[_find_region_price(title, norm, region.code) for _, title, norm in to_search]),
    )

    region_prices: list[tuple[int, RegionPrice]] = []

    for (game_id, _), result in zip(chosen.items(), info_results):
        if result is None:
            continue
        _, rp = result
        if rp is not None:
            region_prices.append((game_id, rp))

    for (game_id, _, normalized_title), rp in zip(to_search, search_results):
        if rp is None:
            logger.info(
                "sync fallback: no match for game_id=%d normalized=%r region=%s",
                game_id, normalized_title, region.code,
            )
            region_sync_not_found.inc()
            continue
        region_prices.append((game_id, rp))

    created = 0
    for game_id, rp in region_prices:
        if region.currency is None and rp.currency is not None:
            region.currency = rp.currency
        session.add(_make_game_region(game_id, region.id, rp))
        created += 1

    if created:
        await session.commit()
        logger.info(
            "synced %d game_region(s) for region=%s telegram_id=%d",
            created, region.code, user.telegram_id,
        )
    else:
        logger.info(
            "sync: no games available in region=%s telegram_id=%d",
            region.code, user.telegram_id,
        )
