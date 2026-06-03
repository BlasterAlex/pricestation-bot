import asyncio
import logging
import re

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bot.metrics import (
    region_sync_not_found,
    subscriptions_already_exists,
    subscriptions_created,
    subscriptions_removed,
)
from db.models.game import Game
from db.models.game_region import GameRegion
from db.models.region import Region
from db.models.subscription import Subscription
from db.models.user import User
from db.models.user_region import UserRegion
from services.ps_store import GameInfo, RegionPrice, best_ps_id, get_game_info, search_games

logger = logging.getLogger(__name__)

_TRADEMARK_RE = re.compile(r"[™®©]")


def _is_effectively_ascii(title: str) -> bool:
    """Return True if the title is ASCII after stripping trademark/copyright symbols."""
    return _TRADEMARK_RE.sub("", title).isascii()


def _game_filter(composite_key: str, suffix: str | None):
    """SQLAlchemy WHERE clause that matches a game by suffix (primary) or composite_key (fallback)."""
    f = Game.composite_key == composite_key
    if suffix:
        f = or_(Game.ps_id_suffix == suffix, f)
    return f


def _make_game_region(game_id: int, region_id: int, rp: RegionPrice) -> GameRegion:
    return GameRegion(
        game_id=game_id,
        region_id=region_id,
        ps_id=rp.ps_id,
        current_price=rp.price,
        base_price=rp.base_price,
        discount_text=rp.discount_text,
        discount_end=rp.discount_end,
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

    Lookup order:
      1. By ps_id_suffix — survives title localization.
      2. By composite_key — fallback for games whose ps_ids have no common suffix.
    """
    composite_key = game_info.composite_key
    suffix = game_info.ps_id_suffix
    region_codes = list(prices.keys())

    # Single query: game + its game_regions (with region) + subscription for this user.
    # Prefer suffix match so localized-title variants collapse to the same game row.
    stmt = (
        select(Game, GameRegion, Region, Subscription)
        .outerjoin(GameRegion, GameRegion.game_id == Game.id)
        .outerjoin(Region, Region.id == GameRegion.region_id)
        .outerjoin(
            Subscription,
            (Subscription.game_id == Game.id) & (Subscription.user_id == user.id),
        )
        .where(_game_filter(composite_key, suffix))
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        # Game doesn't exist yet — create game, game_regions, and subscription
        game = Game(
            title=game_info.title,
            composite_key=composite_key,
            ps_id_suffix=suffix,
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

    # Prefer effectively-ASCII or canonical (en-us) title over non-ASCII stored title.
    # Strip trademark symbols (™, ®, ©) before the ASCII check so titles like
    # "Spider-Man™" are treated as ASCII and can replace non-ASCII stored titles.
    new_is_ascii = _is_effectively_ascii(game_info.title)
    stored_is_ascii = _is_effectively_ascii(game.title)
    if not stored_is_ascii and game_info.title != game.title and (new_is_ascii or "en-us" in prices):
        logger.info("updating title for game_id=%d: %r -> %r", game.id, game.title, game_info.title)
        game.title = game_info.title

    # Back-fill suffix if the game row was created before this field existed
    if suffix and game.ps_id_suffix is None:
        logger.info("setting ps_id_suffix=%r for game_id=%d", suffix, game.id)
        game.ps_id_suffix = suffix

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


async def is_subscribed(
    session: AsyncSession,
    telegram_id: int,
    composite_key: str,
    suffix: str | None = None,
) -> int | None:
    """Return game_id if subscribed, None otherwise."""
    stmt = (
        select(Subscription.game_id)
        .join(Game, Game.id == Subscription.game_id)
        .join(User, User.id == Subscription.user_id)
        .where(_game_filter(composite_key, suffix))
        .where(User.telegram_id == telegram_id)
    )
    return await session.scalar(stmt)


async def unsubscribe_from_game(
    session: AsyncSession,
    telegram_id: int,
    game_id: int,
) -> bool:
    """Delete subscription by game_id. Returns True if it existed, False otherwise."""
    stmt = (
        select(Subscription)
        .join(User, User.id == Subscription.user_id)
        .where(Subscription.game_id == game_id)
        .where(User.telegram_id == telegram_id)
    )
    sub = (await session.scalar(stmt))
    if sub is None:
        return False
    await session.delete(sub)
    await session.commit()
    logger.info("unsubscribed telegram_id=%d from game_id=%d", telegram_id, game_id)
    subscriptions_removed.inc()
    return True


async def get_user_subscriptions_page(
    session: AsyncSession,
    telegram_id: int,
    page: int,
    page_size: int,
) -> tuple[int, list[tuple[GameInfo, dict[str, RegionPrice]]]]:
    """Return (total, [(GameInfo, {region_code: RegionPrice})]) for the given page.

    Results are sorted by subscription date desc (newest first).
    Prices are read from game_regions in the DB — may be stale.
    """
    count_stmt = (
        select(func.count(Subscription.id))
        .join(User, User.id == Subscription.user_id)
        .where(User.telegram_id == telegram_id)
    )
    total: int = (await session.scalar(count_stmt)) or 0
    if total == 0:
        return 0, []

    page_stmt = (
        select(Game, Subscription.created_at)
        .join(Subscription, Subscription.game_id == Game.id)
        .join(User, User.id == Subscription.user_id)
        .where(User.telegram_id == telegram_id)
        .order_by(Subscription.created_at.desc())
        .limit(page_size)
        .offset(page * page_size)
    )
    page_rows = (await session.execute(page_stmt)).all()
    if not page_rows:
        return total, []

    game_ids = [row[0].id for row in page_rows]

    prices_map: dict[int, dict[str, RegionPrice]] = {}
    gr_stmt = (
        select(GameRegion, Region)
        .join(Region, Region.id == GameRegion.region_id)
        .join(UserRegion, UserRegion.region_id == Region.id)
        .join(User, User.id == UserRegion.user_id)
        .where(GameRegion.game_id.in_(game_ids), User.telegram_id == telegram_id)
    )
    for gr, region in (await session.execute(gr_stmt)).all():
        prices_map.setdefault(gr.game_id, {})[region.code] = RegionPrice(
            price=float(gr.current_price) if gr.current_price is not None else None,
            currency=region.currency,
            base_price=float(gr.base_price) if gr.base_price is not None else None,
            discount_text=gr.discount_text,
            ps_id=gr.ps_id,
            discount_end=gr.discount_end,
        )

    result: list[tuple[GameInfo, dict[str, RegionPrice]]] = []
    for game, _ in page_rows:
        game_info = GameInfo(
            title=game.title,
            platforms=game.platforms or [],
            type=game.game_type,
            cover_url=game.cover_url,
            ps_id_suffix=game.ps_id_suffix,
        )
        result.append((game_info, prices_map.get(game.id, {})))
    return total, result


async def _find_region_price(
    title: str,
    region_code: str,
    composite_key: str,
    suffix: str | None
) -> RegionPrice | None:
    """Search PS Store by title and return the RegionPrice for the matching game.

    Fetches the top 5 results for `title` in `region_code` and matches by suffix
    (primary) or composite_key (fallback), consistent with the two-level grouping
    used everywhere else. Returns None if no match is found.
    """
    results = await search_games(title, region_code, page_size=5)
    return next(
        (
            rp for g, rp in results
            if (suffix and g.ps_id_suffix == suffix) or g.composite_key == composite_key
        ),
        None,
    )


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
        select(Game.id, Game.title, Game.composite_key, Game.ps_id_suffix, Region.code, GameRegion.ps_id)
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
    # game_id -> {"title", "composite_key", "suffix", "ps_ids": {region_code: ps_id}}
    game_data: dict[int, dict] = {}
    for game_id, title, composite_key, suffix, region_code, ps_id in rows:
        if game_id not in game_data:
            game_data[game_id] = {
                "title": title,
                "composite_key": composite_key,
                "suffix": suffix,
                "ps_ids": {},
            }
        game_data[game_id]["ps_ids"][region_code] = ps_id

    if not game_data:
        logger.info(
            "sync: all game_regions already exist for region=%s telegram_id=%d",
            region.code, user.telegram_id,
        )
        return

    chosen: dict[int, str] = {}                            # game_id -> ps_id, resolved via get_game_info
    to_search: list[tuple[int, str, str, str | None]] = [] # (game_id, title, composite_key, suffix)

    for game_id, data in game_data.items():
        pid = best_ps_id(region.code, data["ps_ids"])
        if pid:
            chosen[game_id] = pid
        else:
            to_search.append((game_id, data["title"], data["composite_key"], data["suffix"]))

    info_results, search_results = await asyncio.gather(
        asyncio.gather(*[get_game_info(ps_id, region.code) for ps_id in chosen.values()]),
        asyncio.gather(*[
            _find_region_price(title, region.code, composite_key, suffix)
            for _, title, composite_key, suffix in to_search
        ]),
    )

    region_prices: list[tuple[int, RegionPrice]] = []

    for (game_id, _), result in zip(chosen.items(), info_results):
        if result is None:
            continue
        _, rp = result
        if rp is not None:
            region_prices.append((game_id, rp))

    for (game_id, _, composite_key, _suffix), rp in zip(to_search, search_results):
        if rp is None:
            logger.warning(
                "sync fallback: no match for game_id=%d region=%s composite_key=%s suffix=%s",
                game_id, region.code, composite_key, _suffix
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
