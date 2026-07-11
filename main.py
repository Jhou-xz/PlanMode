import asyncio
from bot.client import bot
from bot.handlers import handle_message
from config.settings import settings
from database.core import init_db
from services.scheduler import (
    scheduler,
    schedule_all_daily_summaries,
    schedule_all_memory_compression,
)


@bot.event
async def on_message(message):
    await handle_message(message)


async def main():
    await init_db()
    scheduler.start()
    await schedule_all_daily_summaries()
    await schedule_all_memory_compression()
    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
