"""Integration: auto-add tracked region from a PS Store link locale (real DB).

Unit tests mock region services; this file asserts persistence and orchestration
of `_ensure_tracked_regions` against Postgres.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.ps_store_link import _ensure_tracked_regions
from db.models import Region, UserRegion
from services.region import add_user_region, get_or_create_region, get_user_regions


def _message() -> SimpleNamespace:
    return SimpleNamespace(answer=AsyncMock())


@pytest.mark.asyncio
async def test_ensure_auto_adds_region_and_persists(session: AsyncSession, user, mocker):
    mocker.patch(
        "bot.handlers.ps_store_link.get_ps_regions",
        new=AsyncMock(return_value=[{"name": "United States", "locale": "en-us"}]),
    )
    mock_sync = mocker.patch(
        "bot.handlers.ps_store_link.sync_subscriptions_for_new_region",
        new=AsyncMock(),
    )
    message = _message()

    regions = await _ensure_tracked_regions(message, session, user, "en-us")

    assert len(regions) == 1
    assert regions[0].code == "en-us"
    assert regions[0].name == "United States"

    db_regions = await get_user_regions(session, user.id)
    assert [r.code for r in db_regions] == ["en-us"]

    row = (
        await session.execute(
            select(UserRegion).where(
                UserRegion.user_id == user.id,
                UserRegion.region_id == regions[0].id,
            )
        )
    ).scalar_one_or_none()
    assert row is not None

    mock_sync.assert_awaited_once()
    message.answer.assert_awaited_once_with(
        "Added <b>United States</b> from this link to your tracked regions."
    )


@pytest.mark.asyncio
async def test_ensure_matches_locale_case_insensitively(session: AsyncSession, user, mocker):
    mocker.patch(
        "bot.handlers.ps_store_link.get_ps_regions",
        new=AsyncMock(return_value=[{"name": "United States", "locale": "en-US"}]),
    )
    mocker.patch(
        "bot.handlers.ps_store_link.sync_subscriptions_for_new_region",
        new=AsyncMock(),
    )

    regions = await _ensure_tracked_regions(_message(), session, user, "en-us")

    assert len(regions) == 1
    assert regions[0].code == "en-US"


@pytest.mark.asyncio
async def test_ensure_unknown_locale_does_not_write_db(session: AsyncSession, user, mocker):
    mocker.patch(
        "bot.handlers.ps_store_link.get_ps_regions",
        new=AsyncMock(return_value=[{"name": "United States", "locale": "en-us"}]),
    )
    mock_sync = mocker.patch(
        "bot.handlers.ps_store_link.sync_subscriptions_for_new_region",
        new=AsyncMock(),
    )
    message = _message()

    regions = await _ensure_tracked_regions(message, session, user, "xx-zz")

    assert regions == []
    assert await get_user_regions(session, user.id) == []
    assert (await session.execute(select(Region))).scalars().all() == []
    mock_sync.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        "No regions added yet.\nAdd one in /settings"
    )


@pytest.mark.asyncio
async def test_ensure_skips_catalog_when_user_already_has_region(
    session: AsyncSession, user, mocker
):
    existing = await get_or_create_region(session, "tr-tr", "Turkey")
    await add_user_region(session, user, existing.id)

    mock_catalog = mocker.patch(
        "bot.handlers.ps_store_link.get_ps_regions",
        new=AsyncMock(),
    )
    mock_sync = mocker.patch(
        "bot.handlers.ps_store_link.sync_subscriptions_for_new_region",
        new=AsyncMock(),
    )
    message = _message()

    regions = await _ensure_tracked_regions(message, session, user, "en-us")

    assert [r.code for r in regions] == ["tr-tr"]
    mock_catalog.assert_not_awaited()
    mock_sync.assert_not_awaited()
    message.answer.assert_not_awaited()
