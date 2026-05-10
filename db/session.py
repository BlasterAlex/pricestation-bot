from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
