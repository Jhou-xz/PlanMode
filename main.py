import asyncio
import logging
from logging.handlers import RotatingFileHandler

from bot.client import bot
from bot.handlers import handle_message
from config.settings import settings
from database.core import init_db
from services.scheduler import (
    scheduler,
    schedule_all_daily_summaries,
    schedule_all_memory_compression,
    schedule_all_pending_reminders,
)
from utils.process_guard import ensure_single_instance

LOG_FILE = "/root/plan-mode-project/bot.log"


def setup_logging():
    level = logging.DEBUG if settings.log_level.upper() == "DEBUG" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3),
        ],
    )


@bot.event
async def on_message(message):
    try:
        await handle_message(message)
    except Exception:
        logging.getLogger(__name__).exception("Uncaught error in on_message")


async def main():
    setup_logging()
    ensure_single_instance()
    await init_db()
    scheduler.start()
    await schedule_all_pending_reminders()
    await schedule_all_daily_summaries()
    await schedule_all_memory_compression()
    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
