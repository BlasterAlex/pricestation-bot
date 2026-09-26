import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.formatters import format_game_card
from bot.keyboards.inline import (
    link_editions_keyboard,
    subscribe_keyboard,
    unsubscribe_keyboard,
)
from bot.states.subscription import SearchForm
from clients.ps_regions import get_ps_regions
from clients.ps_store import get_game_info, list_concept_editions
from services.currency import DEFAULT_BASE_CURRENCY, get_rates
from services.ps_link_prices import prices_for_tracked_regions
from services.ps_store import GameInfo, RegionPrice
from services.ps_store_url import PsStoreLinkKind, parse_ps_store_url
from services.region import add_user_region, get_or_create_region, get_user_regions
from services.subscription import is_subscribed, sync_subscriptions_for_new_region
from services.user import get_or_create_user

logger = logging.getLogger(__name__)

router = Router()
_STORE_LINK_ERROR = "Couldn't open this PS Store link. Try again later."


def _is_ps_store_link(message: Message) -> bool:
    return parse_ps_store_url(message.text or "") is not None


async def _ensure_tracked_regions(
    message: Message,
    session: AsyncSession,
    user,
    locale: str,
):
    """If the user has no regions, add the storefront from the shared link."""
    user_regions = await get_user_regions(session, user.id)
    if user_regions:
        return user_regions

    countries = await get_ps_regions()
    country = next(
        (c for c in countries if c["locale"].lower() == locale.lower()),
        None,
    )
    if country is None:
        await message.answer("No regions added yet.\nAdd one in /settings")
        return []

    region = await get_or_create_region(session, country["locale"], country["name"])
    await add_user_region(session, user, region.id)
    await sync_subscriptions_for_new_region(session, user, region)
    await message.answer(
        f"Added <b>{country['name']}</b> from this link to your tracked regions."
    )
    return await get_user_regions(session, user.id)


@router.message(_is_ps_store_link)
async def on_store_link(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    link = parse_ps_store_url(message.text or "")
    if link is None:
        return

    # Sharing a Store link is an explicit new intent — drop any in-progress
    # dialog (search query, region search, currency input, etc.).
    await state.clear()

    user = await get_or_create_user(
        session,
        message.from_user.id,
        message.from_user.username,
    )
    await session.commit()

    user_regions = await _ensure_tracked_regions(message, session, user, link.locale)
    if not user_regions:
        return

    region_codes = [region.code for region in user_regions]
    base_currency = user.preferred_currency or DEFAULT_BASE_CURRENCY

    if link.kind is PsStoreLinkKind.CONCEPT:
        assert link.concept_id is not None
        try:
            editions = await list_concept_editions(link.concept_id, link.locale)
        except Exception:
            logger.exception(
                "Failed to resolve PS Store concept [concept_id=%s locale=%s]",
                link.concept_id,
                link.locale,
            )
            await message.answer(_STORE_LINK_ERROR)
            return

        if not editions:
            await message.answer("Nothing found for this link.")
            return

        rates = await get_rates()
        if len(editions) == 1:
            game, seed_price = editions[0]
            if not seed_price.ps_id:
                await message.answer(_STORE_LINK_ERROR)
                return
            try:
                prices = await prices_for_tracked_regions(
                    game,
                    seed_price.ps_id,
                    link.locale,
                    region_codes,
                )
            except Exception:
                logger.exception(
                    "Failed to load PS Store concept prices [ps_id=%s locale=%s]",
                    seed_price.ps_id,
                    link.locale,
                )
                await message.answer(_STORE_LINK_ERROR)
                return
            if not prices:
                await message.answer("Nothing found for this link.")
                return
            await send_resolved_game_card(
                message,
                state,
                session,
                game,
                prices,
                rates,
                base_currency,
            )
            return

        if any(seed_price.ps_id is None for _, seed_price in editions):
            await message.answer(_STORE_LINK_ERROR)
            return
        await state.set_state(SearchForm.showing_results)
        await state.update_data(
            link_editions=[
                {"game": game.to_dict(), "seed_ps_id": seed_price.ps_id}
                for game, seed_price in editions
            ],
            link_locale=link.locale,
            rates=rates,
            base_currency=base_currency,
        )
        await message.answer(
            "Choose edition:",
            reply_markup=link_editions_keyboard([game for game, _ in editions]),
        )
        return

    assert link.ps_id is not None
    try:
        info = await get_game_info(link.ps_id, link.locale)
    except Exception:
        logger.exception(
            "Failed to resolve PS Store product [ps_id=%s locale=%s]",
            link.ps_id,
            link.locale,
        )
        await message.answer(_STORE_LINK_ERROR)
        return
    if info is None:
        await message.answer("Couldn't open this PS Store link.")
        return

    game, _ = info
    try:
        prices = await prices_for_tracked_regions(
            game,
            link.ps_id,
            link.locale,
            region_codes,
        )
    except Exception:
        logger.exception(
            "Failed to load PS Store product prices [ps_id=%s locale=%s]",
            link.ps_id,
            link.locale,
        )
        await message.answer(_STORE_LINK_ERROR)
        return
    if not prices:
        await message.answer("Nothing found for this link.")
        return

    await send_resolved_game_card(
        message,
        state,
        session,
        game,
        prices,
        await get_rates(),
        base_currency,
    )


@router.callback_query(F.data.startswith("link_edition:"))
async def on_link_edition(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    data = await state.get_data()
    editions = data.get("link_editions", [])

    try:
        index = int(callback.data.split(":", 1)[1])
        if index < 0:
            raise IndexError
        entry = editions[index]
    except (AttributeError, IndexError, TypeError, ValueError):
        await callback.message.answer("Edition not found. Open the link again.")
        return

    game = GameInfo.from_dict(entry["game"])
    seed_ps_id = entry.get("seed_ps_id")
    locale = data.get("link_locale")
    if not seed_ps_id or not locale:
        await callback.message.answer(_STORE_LINK_ERROR)
        return

    user = await get_or_create_user(
        session,
        callback.from_user.id,
        callback.from_user.username,
    )
    await session.commit()
    user_regions = await get_user_regions(session, user.id)
    if not user_regions:
        await callback.message.answer("No regions added yet.\nAdd one in /settings")
        return

    try:
        prices = await prices_for_tracked_regions(
            game,
            seed_ps_id,
            locale,
            [region.code for region in user_regions],
        )
    except Exception:
        logger.exception(
            "Failed to load selected PS Store edition [ps_id=%s locale=%s]",
            seed_ps_id,
            locale,
        )
        await callback.message.answer(_STORE_LINK_ERROR)
        return
    if not prices:
        await callback.message.answer("Nothing found for this link.")
        return

    await send_resolved_game_card(
        callback.message,
        state,
        session,
        game,
        prices,
        data.get("rates"),
        data.get("base_currency", DEFAULT_BASE_CURRENCY),
        actor=callback.from_user,
    )


async def send_resolved_game_card(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    game: GameInfo,
    prices: dict[str, RegionPrice],
    rates: dict[str, float] | None,
    base_currency: str,
    *,
    actor=None,
) -> None:
    has_discount = any(price.base_price is not None for price in prices.values())
    has_end = any(price.discount_end is not None for price in prices.values())
    if has_discount and not has_end:
        sample = next(
            (
                (locale, price)
                for locale, price in prices.items()
                if price.base_price is not None and price.ps_id
            ),
            None,
        )
        if sample:
            result = await get_game_info(sample[1].ps_id, sample[0])
            if result:
                _, info_price = result
                if info_price and info_price.discount_end:
                    for price in prices.values():
                        if price.base_price is not None:
                            price.discount_end = info_price.discount_end

    entries = [
        {
            "game": game.to_dict(),
            "prices": {region: price.to_dict() for region, price in prices.items()},
        }
    ]
    await state.set_state(SearchForm.showing_results)
    await state.update_data(
        entries=entries,
        rates=rates,
        base_currency=base_currency,
    )

    actor = actor or message.from_user
    user = await get_or_create_user(
        session,
        actor.id,
        actor.username,
    )
    await session.commit()
    caption = format_game_card(
        game,
        prices,
        rates,
        footer="Want to track prices in more regions?\nAdd a new one: /add_region",
        base_currency=base_currency,
        show_cross_region_saves=user.show_cross_region_saves,
    )
    game_id = await is_subscribed(
        session,
        actor.id,
        game.composite_key,
        game.ps_id_suffix,
    )
    keyboard = unsubscribe_keyboard(game_id) if game_id else subscribe_keyboard(0)

    if game.cover_url:
        await message.answer_photo(
            photo=game.cover_url,
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await message.answer(caption, reply_markup=keyboard)
