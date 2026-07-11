import asyncio
from bot.client import bot
from bot.handlers import handle_message
from config.settings import settings
from database.core import init_db


@bot.event
async def on_message(message):
    await handle_message(message)


async def main():
    await init_db()
    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
