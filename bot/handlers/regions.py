from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import (
    cancel_keyboard,
    ps_regions_keyboard,
    user_regions_keyboard,
)
from bot.states.subscription import RegionForm
from services.ps_api import get_ps_regions
from services.region import (
    add_user_region,
    get_or_create_region,
    get_user_regions,
    remove_user_region,
)
from services.user import get_or_create_user

router = Router()


@router.message(Command("add_region"))
async def cmd_add_region(message: Message, state: FSMContext) -> None:
    await state.set_state(RegionForm.waiting_for_search)
    await message.answer(
        "Type a country name to search:",
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("my_regions"))
async def cmd_my_regions(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    await session.commit()

    regions = await get_user_regions(session, user.id)
    if not regions:
        await message.answer(
            "You have no tracked regions yet.\n"
            "Add one with /add_region"
        )
        return

    await message.answer(
        "Your regions (tap to remove):\n\n"
        "➕ Add a new one: /add_region",
        reply_markup=user_regions_keyboard(regions),
    )


@router.message(RegionForm.waiting_for_search)
async def on_region_search(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    query = message.text.strip().lower()
    if not query:
        return

    user = await get_or_create_user(
        session, message.from_user.id, message.from_user.username
    )
    await session.commit()

    user_regions = await get_user_regions(session, user.id)
    tracked_locales = {r.code for r in user_regions}

    all_countries = await get_ps_regions()
    matches = [c for c in all_countries if query in c["name"].lower()]

    if not matches:
        await message.answer(
            "No results found. Try a different name:",
            reply_markup=cancel_keyboard(),
        )
        return

    keyboard = ps_regions_keyboard(matches, tracked_locales=tracked_locales)
    await message.answer(
        f"Found {len(matches)} region(s). Choose one:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Cancelled.")


@router.callback_query(F.data.startswith("region_add:"))
async def on_region_add(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    locale = callback.data.split(":", 1)[1]

    all_countries = await get_ps_regions()
    country = next((c for c in all_countries if c["locale"] == locale), None)
    if country is None:
        await callback.answer("Unknown region.", show_alert=True)
        return

    user = await get_or_create_user(
        session, callback.from_user.id, callback.from_user.username
    )
    await session.commit()

    region = await get_or_create_region(session, locale, country["name"])
    added = await add_user_region(session, user.id, region.id)

    await state.clear()

    if added:
        await callback.message.edit_text(
            f"✓ <b>{country['name']}</b> added to your tracked regions.\n\n"
            "View your regions: /my_regions"
        )
    else:
        await callback.answer("This region is already in your list.", show_alert=True)


@router.callback_query(F.data.startswith("region_remove:"))
async def on_region_remove(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    region_id = int(callback.data.split(":", 1)[1])

    user = await get_or_create_user(
        session, callback.from_user.id, callback.from_user.username
    )
    await session.commit()

    await remove_user_region(session, user.id, region_id)

    regions = await get_user_regions(session, user.id)
    if not regions:
        await callback.message.edit_text(
            "You have no tracked regions yet.\n"
            "Add one with /add_region"
        )
        return

    await callback.message.edit_reply_markup(
        reply_markup=user_regions_keyboard(regions)
    )
    await callback.answer()
