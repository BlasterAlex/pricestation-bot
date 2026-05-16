import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.region import (
    add_user_region,
    get_or_create_region,
    get_user_regions,
    remove_user_region,
)
from services.user import get_or_create_user


@pytest.mark.asyncio
async def test_get_or_create_region_creates(session: AsyncSession):
    region = await get_or_create_region(session, "en-us", "United States")
    assert region.id is not None
    assert region.code == "en-us"
    assert region.name == "United States"


@pytest.mark.asyncio
async def test_get_or_create_region_idempotent(session: AsyncSession):
    r1 = await get_or_create_region(session, "en-us", "United States")
    r2 = await get_or_create_region(session, "en-us", "United States")
    assert r1.id == r2.id


@pytest.mark.asyncio
async def test_get_user_regions_empty(session: AsyncSession, user):
    regions = await get_user_regions(session, user.id)
    assert regions == []


@pytest.mark.asyncio
async def test_add_user_region(session: AsyncSession, user, region):
    added = await add_user_region(session, user, region.id)
    assert added is True

    regions = await get_user_regions(session, user.id)
    assert len(regions) == 1
    assert regions[0].id == region.id


@pytest.mark.asyncio
async def test_add_user_region_duplicate(session: AsyncSession, user, region):
    await add_user_region(session, user, region.id)
    added = await add_user_region(session, user, region.id)
    assert added is False


@pytest.mark.asyncio
async def test_remove_user_region(session: AsyncSession, user, region):
    await add_user_region(session, user, region.id)
    await remove_user_region(session, user, region.id)

    regions = await get_user_regions(session, user.id)
    assert regions == []


@pytest.mark.asyncio
async def test_remove_user_region_nonexistent(session: AsyncSession, user, region):
    await remove_user_region(session, user, region.id)

    regions = await get_user_regions(session, user.id)
    assert regions == []


@pytest.mark.asyncio
async def test_get_or_create_user_creates(session: AsyncSession):
    user = await get_or_create_user(session, 999888777, "newuser")
    assert user.id is not None
    assert user.telegram_id == 999888777
    assert user.username == "newuser"


@pytest.mark.asyncio
async def test_get_or_create_user_idempotent(session: AsyncSession):
    u1 = await get_or_create_user(session, 999888777, "newuser")
    u2 = await get_or_create_user(session, 999888777, "newuser")
    assert u1.id == u2.id
