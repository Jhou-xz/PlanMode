import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from config.settings import settings
from database.models import Memory, Idea, Reminder, Message, User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool, echo=False)
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_session() as s:
        yield s
        # Clean up after each test to avoid cross-test contamination
        await s.execute(delete(Memory))
        await s.execute(delete(Idea))
        await s.execute(delete(Reminder))
        await s.execute(delete(Message))
        await s.execute(delete(User))
        await s.commit()
    await test_engine.dispose()
