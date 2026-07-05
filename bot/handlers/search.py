import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_card, format_game_list
from bot.keyboards.inline import search_results_keyboard, subscribe_keyboard, unsubscribe_keyboard
from bot.states.subscription import SearchForm
from services.currency import DEFAULT_BASE_CURRENCY, get_rates
from services.ps_store import GameInfo, RegionPrice, best_ps_id, get_game_info, search_games
from services.region import get_user_regions
from services.subscription import is_subscribed
from services.user import get_or_create_user

_CANONICAL_REGION = "en-us"
_MAX_SEARCH_RESULTS = 15

router = Router()


def aggregate_search_results(
    region_codes: list[str],
    results: list[list[tuple[GameInfo, RegionPrice]]],
    us_results: list[tuple[GameInfo, RegionPrice]] | None = None,
) -> tuple[
    dict[str, dict[str, RegionPrice]],  # by_key:        suffix or composite_key → {region → RegionPrice}
    dict[str, GameInfo],                # rep_game:      suffix or composite_key → representative GameInfo
    dict[str, dict[str, str]],          # ps_ids_by_key: suffix or composite_key → {region → ps_id}
]:
    """Merge per-region search results into deduplicated game cards.

    Canonical source — ``en-us``:
      ``en-us`` is always processed first (prepended from *us_results* when the
      user hasn't added that region, or moved to the front when they have).
      Its ``GameInfo`` (title, composite_key, cover) becomes the authoritative
      representative for any card it covers, giving consistent English titles and
      composite keys regardless of which locale a user subscribes from.
      Prices from ``en-us`` are only exposed in *by_key* when it is present in
      *region_codes* (i.e. the user has actually added that region).

    Two-level merge:

    Level 1 — ps_id suffix (e.g. ``"25STANDARDBUNDLE"``).
      Shared across regional prefixes (UP/EP/HP/JP) for the same product,
      so it collapses localised-title variants into one card. Falls back to
      composite_key when the suffix differs per region (BG3, Lies of P, etc.).

    Level 2 — ``composite_key`` = (norm_title, type, platforms).
      Fallback when ps_id suffixes differ. ``en-us`` still wins rep_game.

    When ``en-us`` has no result for a game, ASCII-title preference applies.

    Args:
        region_codes:  codes of the user's own regions (prices shown for these).
        results:       per-region search results, aligned with *region_codes*.
        us_results:    ``en-us`` results fetched separately; ``None`` when
                       ``en-us`` is already in *region_codes*.
    """
    by_key: dict[str, dict[str, RegionPrice]] = {}
    rep_game: dict[str, GameInfo] = {}
    ps_ids_by_key: dict[str, dict[str, str]] = {}
    suffix_to_key: dict[str, str] = {}

    user_codes = set(region_codes)

    # Build ordered processing list: en-us always first for canonical priority.
    if us_results is not None:
        # en-us not in user regions → prepend, prices hidden
        ordered_codes = [_CANONICAL_REGION] + list(region_codes)
        ordered_results = [us_results] + list(results)
    elif _CANONICAL_REGION in user_codes:
        # en-us in user regions → move to front
        idx = list(region_codes).index(_CANONICAL_REGION)
        ordered_codes = [_CANONICAL_REGION] + [c for c in region_codes if c != _CANONICAL_REGION]
        ordered_results = [results[idx]] + [r for i, r in enumerate(results) if i != idx]
    else:
        ordered_codes = list(region_codes)
        ordered_results = list(results)

    for region_code, region_games in zip(ordered_codes, ordered_results):
        show_prices = region_code in user_codes

        for game, price in region_games:
            sfx = game.ps_id_suffix
            if sfx and sfx in suffix_to_key:
                key = suffix_to_key[sfx]
            else:
                key = game.composite_key
                if sfx:
                    suffix_to_key[sfx] = key

            # en-us unconditionally wins rep_game; otherwise prefer ASCII title
            if region_code == _CANONICAL_REGION or key not in rep_game:
                rep_game[key] = game
            elif game.title.isascii() and not rep_game[key].title.isascii():
                rep_game[key] = game

            if show_prices:
                by_key.setdefault(key, {})[region_code] = price
                if price.ps_id:
                    ps_ids_by_key.setdefault(key, {})[region_code] = price.ps_id

    return by_key, rep_game, ps_ids_by_key


async def _do_search(message: Message, state: FSMContext, session: AsyncSession, query: str) -> None:
    user = await get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    await session.commit()

    user_regions = await get_user_regions(session, user.id)

    if not user_regions:
        await message.answer("No regions added yet.\nAdd one in /settings")
        return

    user_region_codes = [r.code for r in user_regions]

    # en-us is always fetched to provide canonical titles, composite_keys and suffixes.
    # If the user already has en-us, its results arrive with the main gather and
    # aggregate_search_results moves them to the front automatically.
    # Otherwise we issue an extra request whose results are passed as us_results —
    # they inform grouping and rep_game but are not shown as prices to the user.
    needs_us = _CANONICAL_REGION not in user_region_codes

    if needs_us:
        results, us_results, rates = await asyncio.gather(
            asyncio.gather(*[search_games(query, r.code) for r in user_regions]),
            search_games(query, _CANONICAL_REGION),
            get_rates(),
        )
    else:
        results, rates = await asyncio.gather(
            asyncio.gather(*[search_games(query, r.code) for r in user_regions]),
            get_rates(),
        )
        us_results = None

    by_key, rep_game, ps_ids_by_key = aggregate_search_results(
        user_region_codes, results, us_results
    )

    # Trim to display limit before fallback to avoid unnecessary requests
    all_keys = list(rep_game)
    visible_keys = set(all_keys[:_MAX_SEARCH_RESULTS])

    # Fallback: for regions that didn't find a game by name, try fetching by ps_id.
    fallback_tasks: list[tuple[str, object, str]] = []
    for key, found in by_key.items():
        if key not in visible_keys:
            continue
        for region in user_regions:
            if region.code not in found:
                best = best_ps_id(region.code, ps_ids_by_key[key])
                if best:
                    fallback_tasks.append((key, region, best))

    if fallback_tasks:
        fallback_results = await asyncio.gather(*[
            get_game_info(ps_id, region.code)
            for _, region, ps_id in fallback_tasks
        ])
        for (key, region, _), result in zip(fallback_tasks, fallback_results):
            if result is not None:
                _, region_price = result
                by_key[key][region.code] = region_price

    all_games = [rep_game[k] for k in all_keys]
    games = all_games[:_MAX_SEARCH_RESULTS]
    visible_keys = all_keys[:_MAX_SEARCH_RESULTS]

    entries = [
        {
            "game": rep_game[key].to_dict(),
            "prices": {r: rp.to_dict() for r, rp in by_key[key].items()},
        }
        for key in visible_keys
    ]

    base_currency = user.preferred_currency or DEFAULT_BASE_CURRENCY

    await state.set_state(SearchForm.showing_results)
    await state.update_data(entries=entries, rates=rates, base_currency=base_currency)

    hidden = len(all_games) - len(games)
    footer = "Want to track prices in more regions?\nAdd a new one in /settings"
    if hidden:
        notice = f"<b>Showing {len(games)} of {len(all_games)} results</b>. Refine your query to see more."
        footer = f"{notice}\n\n{footer}"

    text = format_game_list(
        title="Select a game to see details:",
        footer=footer,
        games=games,
        prices=[by_key[k] for k in visible_keys],
        rates=rates,
        base_currency=base_currency,
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
async def on_game_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()

    data = await state.get_data()
    entries = data.get("entries", [])
    rates = data.get("rates")
    base_currency = data.get("base_currency", DEFAULT_BASE_CURRENCY)

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
                    entries[index]["prices"] = {r: rp.to_dict() for r, rp in prices.items()}
                    await state.update_data(entries=entries)

    user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
    caption = format_game_card(
        game,
        prices,
        rates,
        footer="Want to track prices in more regions?\nAdd a new one: /add_region",
        base_currency=base_currency,
        show_cross_region_saves=user.show_cross_region_saves,
    )
    game_id = await is_subscribed(session, callback.from_user.id, game.composite_key, game.ps_id_suffix)
    keyboard = unsubscribe_keyboard(game_id) if game_id else subscribe_keyboard(index)

    if game.cover_url:
        await callback.message.answer_photo(photo=game.cover_url, caption=caption, reply_markup=keyboard)
    else:
        await callback.message.answer(caption, reply_markup=keyboard)
