import asyncio

from clients.ps_store import get_game_info, search_games
from services.ps_store import (
    GameInfo,
    RegionPrice,
    preferred_ps_prefix,
    remap_ps_id_prefix,
)


async def _price_for_region(
    game: GameInfo,
    seed_ps_id: str,
    seed_locale: str,
    region_code: str,
) -> tuple[str, RegionPrice | None]:
    candidate_id = (
        seed_ps_id
        if region_code == seed_locale
        else remap_ps_id_prefix(seed_ps_id, preferred_ps_prefix(region_code))
    )
    product = await get_game_info(candidate_id, region_code)
    if product is not None:
        return region_code, product[1]

    results = await search_games(game.title, region_code)
    match = None
    if game.ps_id_suffix is not None:
        match = next(
            (item for item in results if item[0].ps_id_suffix == game.ps_id_suffix),
            None,
        )
    if match is None:
        match = next(
            (item for item in results if item[0].composite_key == game.composite_key),
            None,
        )
    return region_code, match[1] if match is not None else None


async def prices_for_tracked_regions(
    game: GameInfo,
    seed_ps_id: str,
    seed_locale: str,
    region_codes: list[str],
) -> dict[str, RegionPrice]:
    region_prices = await asyncio.gather(
        *(
            _price_for_region(game, seed_ps_id, seed_locale, region_code)
            for region_code in region_codes
        ),
        return_exceptions=True,
    )
    return {
        result[0]: result[1]
        for result in region_prices
        if not isinstance(result, BaseException) and result[1] is not None
    }
