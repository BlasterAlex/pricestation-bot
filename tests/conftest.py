import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from db.base import Base
from db.models import Game, Region, User

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        yield s


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    u = User(telegram_id=123456789, username="testuser")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def game(session: AsyncSession):
    g = Game(ps_id="EP0001-CUSA00001_00", title="Test Game")
    session.add(g)
    await session.flush()
    return g


@pytest_asyncio.fixture
async def region(session: AsyncSession):
    r = Region(code="TR", name="Турция", currency="TRY")
    session.add(r)
    await session.flush()
    return r
