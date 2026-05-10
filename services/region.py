from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Region, UserRegion


async def get_or_create_region(
    session: AsyncSession, locale: str, name: str
) -> Region:
    result = await session.execute(select(Region).where(Region.code == locale))
    region = result.scalar_one_or_none()
    if region is None:
        region = Region(code=locale, name=name)
        session.add(region)
        await session.flush()
    return region


async def get_user_regions(session: AsyncSession, user_id: int) -> list[Region]:
    result = await session.execute(
        select(Region)
        .join(UserRegion, UserRegion.region_id == Region.id)
        .where(UserRegion.user_id == user_id)
        .order_by(Region.name)
    )
    return list(result.scalars().all())


async def remove_user_region(
    session: AsyncSession, user_id: int, region_id: int
) -> None:
    result = await session.execute(
        select(UserRegion).where(
            UserRegion.user_id == user_id,
            UserRegion.region_id == region_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()


async def add_user_region(
    session: AsyncSession, user_id: int, region_id: int
) -> bool:
    exists = await session.execute(
        select(UserRegion).where(
            UserRegion.user_id == user_id,
            UserRegion.region_id == region_id,
        )
    )
    if exists.scalar_one_or_none() is not None:
        return False
    session.add(UserRegion(user_id=user_id, region_id=region_id))
    await session.commit()
    return True
