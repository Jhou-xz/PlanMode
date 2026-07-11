import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from database.core import async_session


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with async_session() as s:
        yield s
