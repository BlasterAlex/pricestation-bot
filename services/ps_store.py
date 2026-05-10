import aiohttp


async def search_games(query: str, region: str) -> list[dict]:
    raise NotImplementedError


async def get_game_price(ps_id: str, region: str) -> float | None:
    raise NotImplementedError
