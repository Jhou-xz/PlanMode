import asyncio
from database.core import init_db


async def main():
    await init_db()
    print("database initialized")


if __name__ == "__main__":
    asyncio.run(main())
