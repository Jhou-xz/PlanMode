import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from config.settings import settings
from database.models import Memory, Item, Reminder, Message, User, Section, Base


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool, echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_session() as s:
        yield s
        # Clean up after each test to avoid cross-test contamination
        # Delete child tables with foreign keys before parent tables.
        await s.execute(delete(Reminder))
        await s.execute(delete(Memory))
        await s.execute(delete(Item))
        await s.execute(delete(Message))
        await s.execute(delete(Section))
        await s.execute(delete(User))
        await s.commit()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
