import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_card, format_game_list
from bot.keyboards.inline import search_results_keyboard
from bot.states.subscription import SearchForm
from services.currency import get_rates
from services.ps_store import GameInfo, RegionPrice, get_game_info, normalize_title, search_games
from services.region import get_user_regions
from services.user import get_or_create_user

# PS Store product ID prefixes by region group
_COUNTRY_TO_PS_PREFIX: dict[str, str] = {
    "us": "UP", "ca": "UP", "mx": "UP", "br": "UP", "ar": "UP", "cl": "UP", "co": "UP",
    "jp": "JP",
    "kr": "KP",
}


def _best_ps_id(region_code: str, ps_ids: dict[str, str]) -> str | None:
    country = region_code.split("-")[-1].lower()
    preferred = _COUNTRY_TO_PS_PREFIX.get(country, "EP")
    return next((pid for pid in ps_ids.values() if pid.startswith(preferred)), None)


_MAX_SEARCH_RESULTS = 15

router = Router()


async def _do_search(message: Message, state: FSMContext, session: AsyncSession, query: str) -> None:
    user = await get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    await session.commit()

    user_regions = await get_user_regions(session, user.id)

    if not user_regions:
        await message.answer("No regions added yet.\nAdd one with /add_region")
        return

    results, rates = await asyncio.gather(
        asyncio.gather(*[search_games(query, region.code) for region in user_regions]),
        get_rates(),
    )

    # Merge results across regions by normalized title
    by_title: dict[str, dict[str, RegionPrice]] = {}
    rep_game: dict[str, GameInfo] = {}
    ps_ids_by_title: dict[str, dict[str, str]] = {}

    for region, region_games in zip(user_regions, results):
        for game, price in region_games:
            key = normalize_title(game.title)
            # Don't overwrite a paid price with a free/unavailable one
            if price.price is not None or region.code not in by_title.get(key, {}):
                by_title.setdefault(key, {})[region.code] = price
            # Prefer ASCII title so localized prefixes ("Набір", "세트" etc.) don't win
            if key not in rep_game or game.title.isascii():
                rep_game[key] = game
            if price.ps_id:
                ps_ids_by_title.setdefault(key, {})[region.code] = price.ps_id

    # Trim to display limit before fallback to avoid unnecessary requests
    all_keys = list(rep_game)
    visible_keys = set(all_keys[:_MAX_SEARCH_RESULTS])

    # Fallback: for regions that didn't find a game by name, try fetching by ps_id.
    fallback_tasks: list[tuple[str, object, str]] = []
    for title_key, found in by_title.items():
        if title_key not in visible_keys:
            continue
        for region in user_regions:
            if region.code not in found:
                best = _best_ps_id(region.code, ps_ids_by_title[title_key])
                if best:
                    fallback_tasks.append((title_key, region, best))

    if fallback_tasks:
        fallback_results = await asyncio.gather(*[
            get_game_info(ps_id, region.code)
            for _, region, ps_id in fallback_tasks
        ])
        for (title_key, region, _), result in zip(fallback_tasks, fallback_results):
            if result is not None:
                _, region_price = result
                if region_price is not None:
                    by_title[title_key][region.code] = region_price

    # Exclude games with no purchasable price in any of the user's regions (free games, demos, removed titles).
    all_keys = [k for k in all_keys if any(rp.price is not None for rp in by_title.get(k, {}).values())]

    all_games = [rep_game[k] for k in all_keys]
    games = all_games[:_MAX_SEARCH_RESULTS]
    visible_keys = all_keys[:_MAX_SEARCH_RESULTS]

    entries = [
        {
            "game": rep_game[key].to_dict(),
            "prices": {r: rp.to_dict() for r, rp in by_title[key].items()},
        }
        for key in visible_keys
    ]

    await state.set_state(SearchForm.showing_results)
    await state.update_data(entries=entries, rates=rates)

    hidden = len(all_games) - len(games)
    footer = "Want to track prices in more regions?\nAdd a new one: /add_region"
    if hidden:
        notice = f"<b>Showing {len(games)} of {len(all_games)} results</b>. Refine your query to see more."
        footer = f"{notice}\n\n{footer}"

    text = format_game_list(
        title="Select a game to see details:",
        footer=footer,
        games=games,
        prices=[by_title[k] for k in visible_keys],
        rates=rates,
    )
    await message.answer(text, reply_markup=search_results_keyboard(games))


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    query = message.text.partition(" ")[2].strip()
    if query:
        await _do_search(message, state, session, query)
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
    await _do_search(message, state, session, query)


@router.callback_query(F.data.startswith("game_select:"))
async def on_game_select(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()
    entries = data.get("entries", [])
    rates = data.get("rates")

    index = int(callback.data.split(":", 1)[1])
    if index >= len(entries):
        await callback.message.answer("Game not found. Please search again.")
        return

    entry = entries[index]
    game = GameInfo.from_dict(entry["game"])
    prices = {region: RegionPrice.from_dict(v) for region, v in entry["prices"].items()}

    # endTime is not in search results — fetch it from one discounted region
    has_discount = any(rp.base_price is not None for rp in prices.values())
    has_end = any(rp.discount_end is not None for rp in prices.values())
    if has_discount and not has_end:
        sample = next(
            ((locale, rp) for locale, rp in prices.items() if rp.base_price is not None and rp.ps_id),
            None,
        )
        if sample:
            result = await get_game_info(sample[1].ps_id, sample[0])
            if result:
                _, info_price = result
                if info_price and info_price.discount_end:
                    for rp in prices.values():
                        if rp.base_price is not None:
                            rp.discount_end = info_price.discount_end

    caption = format_game_card(
        game,
        prices,
        rates,
        footer="Want to track prices in more regions?\nAdd a new one: /add_region",
    )

    if game.cover_url:
        await callback.message.answer_photo(photo=game.cover_url, caption=caption)
    else:
        await callback.message.answer(caption)
