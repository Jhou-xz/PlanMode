import asyncio
from sqlalchemy import text
from database.core import engine


async def test():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 1"))
        print("db ok", r.scalar())


if __name__ == "__main__":
    asyncio.run(test())
